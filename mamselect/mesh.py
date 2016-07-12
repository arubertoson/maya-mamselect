"""
Contains selection tools for working with meshes and surfaces.
"""
import sys
import logging
import collections

from PySide import QtCore, QtGui

import maya.api.OpenMaya as api
from maya import cmds, mel
from maya.OpenMaya import MGlobal

import mampy
from mampy.utils import undoable, repeatable, get_object_under_cursor, DraggerCtx, mvp
from mampy.dgcomps import Component, MeshPolygon
from mampy.dgcontainers import SelectionList
from mampy.exceptions import InvalidSelection


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

optionvar = mampy.optionVar()


@undoable
@repeatable
def adjacent(expand=True):
    """Grow and remove previous selection to get adjacent selection.

    .. todo:: make contractable
    """
    selected = mampy.selected()
    components = list(selected.itercomps())
    if not selected or not components:
        raise InvalidSelection('Select valid mesh component.')

    toggle_components = SelectionList()
    for component in components:
        try:
            adjacent_selection = {
                api.MFn.kMeshPolygonComponent: component.to_edge().to_face(),
                api.MFn.kMeshEdgeComponent: component.to_vert().to_edge(),
                api.MFn.kMeshVertComponent: component.to_edge().to_vert(),
                api.MFn.kMeshMapComponent: component.to_edge().to_map(),
            }[component.type]
            toggle_components.extend(adjacent_selection)
        except KeyError:
            raise InvalidSelection('Select component from mesh object.')

    cmds.select(list(toggle_components), toggle=True)


@undoable
@repeatable
def clear_mesh_or_loop():
    """Clear mesh or loop under mouse."""
    preselect_hilite = mampy.ls(preSelectHilite=True)[0]

    if preselect_hilite.type == api.MFn.kEdgeComponent:
        cmds.polySelect(preselect_hilite.dagpath,
                        edgeLoop=preselect_hilite.index, d=True)
    elif preselect_hilite.type == api.MFn.kMeshPolygonComponent:
        cmds.polySelect(preselect_hilite.dagpath,
                        extendToShell=preselect_hilite.index, d=True)


@undoable
@repeatable
def toggle_mesh_under_cursor():
    """Toggle mesh object under cursor."""
    preselect = mampy.ls(preSelectHilite=True)
    if not preselect:
        under_cursor_mesh = get_object_under_cursor()
        if under_cursor_mesh is None:
            raise InvalidSelection('No valid selection')
        obj = mampy.get_node(under_cursor_mesh)
    else:
        obj = preselect.pop()

    if issubclass(obj.__class__, Component):
        component = obj.get_complete()
        if component.node in mampy.selected():
            cmds.select(list(component), d=True)
        else:
            dagpath = mampy.get_node(component.dagpath)
            cmds.hilite(dagpath.get_transform().name, unHilite=True)
        return
    else:
        cmds.select(obj.name, toggle=True)
        if obj.name in mampy.selected():
            if cmds.selectMode(q=True, component=True):
                cmds.hilite(obj.name)




@undoable
def convert(comptype, **convert_arguments):
    """
    Convert current selection to given comptype.
    """
    ComponentType = collections.namedtuple('ComponentType', ('type', 'function'))
    convert_mode = {
        'vert': ComponentType(api.MFn.kMeshVertComponent, 'to_vert'),
        'edge': ComponentType(api.MFn.kMeshEdgeComponent, 'to_edge'),
        'face': ComponentType(api.MFn.kMeshPolygonComponent, 'to_face'),
        'map': ComponentType(api.MFn.kMeshMapComponent, 'to_map'),
    }[comptype]

    selected, converted = mampy.selected(), SelectionList()
    # s, cl = mampy.selected(), mampy.SelectionList()
    if not selected:
        raise InvalidSelection('Nothing Selected.')

    for component in selected.itercomps():
        if component.type == convert_mode.type:
            return logger.info('{} already active component type.'.format(comptype))

        # Special treatment when converting vert -> edge
        elif ('border' not in convert_arguments and
                component.type == api.MFn.kMeshVertComponent and
                convert_mode.type == api.MFn.kMeshEdgeComponent):
            convert_arguments.update({'internal': True})

        converted.append(getattr(component, convert_mode.function)(**convert_arguments))

    set_selection_mask(comptype)
    cmds.select(list(converted))


@undoable
@repeatable
def flood():
    """Get contiguous components from current selection."""
    selected = mampy.selected()
    if not selected:
        raise InvalidSelection('Select mesh component')

    # extend selected with ``mampy.Component`` objects.
    selected.extend([comp.get_mesh_shell() for comp in selected.itercomps()])
    cmds.select(list(selected))




@undoable
@repeatable
def inbetween():
    """Select components between the last two selections."""
    slist = mampy.ordered_selection(-2)
    if not slist or not len(slist) == 2:
        return logger.warn('Invalid selection, select two mesh components.')

    comptype = slist.itercomps().next().type
    indices = [c.index for c in slist.itercomps()]

    if (comptype in [
            api.MFn.kMeshPolygonComponent,
            api.MFn.kMeshEdgeComponent,
            api.MFn.kMeshVertComponent]):
        # check if a edge ring can be selected.
        if (comptype == api.MFn.kMeshEdgeComponent and
                cmds.polySelect(q=True, edgeRingPath=indices)):
            inbetween = cmds.polySelect(q=True, ass=True, edgeRingPath=indices)
        else:
            inbetween = cmds.polySelectSp(list(slist), q=True, loop=True)
    elif comptype == api.MFn.kMeshMapComponent:
        path = cmds.polySelect(q=True, ass=True, shortestEdgePathUV=indices)
        inbetween = cmds.polyListComponentConversion(path, tuv=True)

    cmds.select(inbetween, add=True)


@undoable
@repeatable
def invert(shell=False):
    """
    Invert selection.

    If shell is active but there are no selections, script assumes we
    want a full invert.

    .. note:: If current selection mask is *object* and there are no
        selections there is no way that I know of to find out the active
        component type.
    """
    slist, hilited = mampy.selected(), mampy.ls(hl=True)
    smask = mampy.get_active_mask()
    ctype = None

    # Try object invert
    if smask.mode == MGlobal.kSelectObjectMode and not hilited:
        dagobjs = cmds.ls(visible=True, assemblies=True)
        if not dagobjs:
            logger.warn('Nothing to invert.')
        else:
            cmds.select(dagobjs, toggle=True)
        return

    # set up component invert
    if smask.mode == MGlobal.kSelectObjectMode and not slist:
        return logger.warn('Switch selection mask from object to component.')
    elif slist:
        ctype = slist.itercomps().next().type
    else:
        for m in smask:
            try:
                ctype = {
                    smask.kSelectMeshVerts: api.MFn.kMeshVertComponent,
                    smask.kSelectMeshEdges: api.MFn.kMeshEdgeComponent,
                    smask.kSelectMeshFaces: api.MFn.kMeshPolygonComponent,
                    smask.kSelectMeshUVs: api.MFn.kMeshMapComponent,
                }[m]
            except KeyError:
                continue
            else:
                break

    # perform component invert
    t = SelectionList()
    if not shell or not slist:
        for dp in hilited:
            t.extend(Component.create(dp, ctype).get_complete())
    else:
        for comp in slist.copy().itercomps():
            t.extend(comp.get_mesh_shell() if shell else comp.get_complete())

    # for some reason the tgl keyword makes cmds.select really fast.
    cmds.select(list(t), tgl=True)


@undoable
@repeatable
def nonquads(ngons=True, query=False):
    """
    Select all nonquads from an object.
    """
    type_ = 3 if ngons else 1

    if query:
        selected = mampy.selected()

    cmds.selectMode(component=True)
    cmds.selectType(facet=True)

    cmds.polySelectConstraint(mode=3, t=0x0008, size=type_)
    cmds.polySelectConstraint(disable=True)
    ngons = mampy.selected()

    if query:
        cmds.select(list(selected))
        return ngons
    sys.stdout.write(str(len(ngons)) + ' N-Gon(s) Selected.\n')


@undoable
@repeatable
def traverse(expand=True, mode='normal'):
    if mode == 'normal':
        if expand:
            return mel.eval('PolySelectTraverse(1)')
        return mel.eval('PolySelectTraverse(2)')
    elif mode == 'adjacent':
        if expand:
            return adjacent(expand)
        return adjacent


if __name__ == '__main__':
    invert(True)
