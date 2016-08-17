"""
Contains selection tools for working with meshes and surfaces.
"""
import sys
import logging
import collections

from maya import cmds, mel
from maya.OpenMaya import MGlobal
import maya.api.OpenMaya as api

import mampy
from mampy._old.utils import undoable, repeatable, get_object_under_cursor
from mampy._old.comps import Component
from mampy._old.containers import SelectionList
from mampy._old.exceptions import InvalidSelection

from mamselect.masks import set_selection_mask

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

optionvar = mampy.optionVar()


class TrackSelectionOrderNotSet(Exception):
    """Raise if track selection order is not set in preferences."""


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


def select_deselect_border_edge(root_edge, tolerance):

    def get_vector_from_edge(edge, index):
        p1, p2 = [edge.mesh.getPoint(x) for x in edge.mesh.getEdgeVertices(index)]
        return p2 - p1

    edge_vector = get_vector_from_edge(root_edge, root_edge.index)
    indices = cmds.polySelect(
        root_edge.dagpath,
        edgeBorder=root_edge.index,
        noSelection=True
    )
    edge = root_edge.new().add(indices)
    edge_to_select = root_edge.new()
    for idx in edge.indices:
        vec = get_vector_from_edge(edge, idx)
        if edge_vector.isParallel(vec, 0.35):
            edge_to_select.add(idx)

    connected = edge_to_select.get_connected()
    for e in connected:
        if root_edge in e:
            print root_edge in mampy.comp_ls()
            if root_edge in mampy.comp_ls():
                cmds.select(list(e), d=True)
            else:
                cmds.select(list(e), add=True)


def select_deselect_edge_lists(root_edge, loop=True):
    kw = {'edgeLoop' if loop else 'edgeRing': root_edge.index}
    if root_edge in mampy.comp_ls():
        kw.update({'deselect': True})
    else:
        kw.update({'add': True})
    cmds.polySelect(
        root_edge.dagpath,
        **kw
    )


def select_deselect_surrounded(root_comp):
    selected = mampy.comp_ls()
    if not selected:
        cmds.select(list(root_comp.get_complete()), add=True)
    else:
        for comp in selected:
            if not root_comp.dagpath == comp.dagpath:
                continue

            if comp.is_complete():
                cmds.select(list(comp), d=True)
            else:
                connected = list(comp.get_connected())
                connected_not_selected = list(comp.toggle().get_connected())

                if any(root_comp in c for c in connected):
                    kw = {'deselect': True}
                    iterable = connected
                elif any(root_comp in c for c in connected_not_selected):
                    kw = {'add': True}
                    iterable = connected_not_selected

                for c in iterable:
                    if root_comp in c:
                        cmds.select(list(c), **kw)


@undoable
@repeatable
def select_deselect_isolated_components(loop=True, tolerance=0.35):
    """Clear mesh or loop under mouse."""
    try:
        preselect_hilite = mampy.comp_ls(preSelectHilite=True).pop()
    except IndexError:
        return logger.warn('Nothing in preselection.')

    if preselect_hilite.type == api.MFn.kMeshEdgeComponent:
        if not loop:
            select_deselect_edge_lists(preselect_hilite, loop)
        elif preselect_hilite.is_border(preselect_hilite.index):
            select_deselect_border_edge(preselect_hilite, tolerance)
        else:
            select_deselect_edge_lists(preselect_hilite, loop)
    else:
        select_deselect_surrounded(preselect_hilite)


@undoable
@repeatable
def toggle_mesh_under_cursor():
    """Toggle mesh object under cursor."""
    preselect = mampy.ls(preSelectHilite=True)
    if not preselect:
        under_cursor_mesh = get_object_under_cursor()
        if under_cursor_mesh is None:
            return
        obj = mampy.get_node(under_cursor_mesh)
        if cmds.selectMode(q=True, component=True):
            cmds.hilite(obj.get_transform().name)
        else:
            cmds.select(obj.name, toggle=True)
    else:
        obj = preselect.iterdags().next()
        trn = obj.get_transform()
        if trn.name in mampy.ls(hl=True):
            cmds.hilite(trn.name, unHilite=True)


def deselect_all_but():
    preselect = mampy.ls(preSelectHilite=True)
    obj = get_object_under_cursor()
    if not obj:
        return

    cmds.select(obj, r=True)
    if not preselect:
        return
    else:
        cmds.hilite(obj, toggle=True)


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
    if list(selected.itercomps())[0].type == api.MFn.kMeshMapComponent:
        selected.extend([comp.get_uv_shell() for comp in selected.itercomps()])
    else:
        selected.extend([comp.get_mesh_shell() for comp in selected.itercomps()])
    cmds.select(list(selected))


@undoable
@repeatable
def inbetween():
    """Select components between the last two selections."""
    if not cmds.selectPref(q=True, trackSelectionOrder=True):
        raise TrackSelectionOrderNotSet('Set track selection order in'
                                        ' preferences.')

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
    select_deselect_isolated_components()
