"""
Contains selection tools for working with meshes and surfaces.
"""
import sys
import logging
import itertools
import collections

from maya import cmds, mel
from maya.OpenMaya import MGlobal
from maya.api.OpenMaya import MFn
import maya.api.OpenMaya as api

import mampy
from mampy.core.selectionlist import ComponentList
from mampy.core.dagnodes import Node
from mampy.core.components import SingleIndexComponent
from mampy.core.exceptions import NothingSelected, InvalidSelection
from mampy.utils import (get_active_flags_in_mask, get_object_under_cursor,
                         undoable, repeatable)


from mamselect.masks import set_selection_mask

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

optionvar = mampy.optionVar()


@undoable()
@repeatable
def adjacent():
    """Grow and remove previous selection to get adjacent selection.

    .. todo:: make contractable
    """
    selected = mampy.complist()
    if not selected:
        raise NothingSelected()

    toggle_components = ComponentList()
    for each in selected:
        try:
            adjacent_selection = {
                MFn.kMeshPolygonComponent: each.to_edge().to_face(),
                MFn.kMeshEdgeComponent: each.to_vert().to_edge(),
                MFn.kMeshVertComponent: each.to_edge().to_vert(),
                MFn.kMeshMapComponent: each.to_edge().to_map(),
            }[each.type]
            toggle_components.append(adjacent_selection)
        except KeyError:
            raise InvalidSelection('Selection must be mesh component.')

    cmds.select(toggle_components.cmdslist(), toggle=True)


def select_deselect_border_edge(root_edge, tolerance):

    def get_vector_from_edge(edge, index):
        p1, p2 = [edge.points[i] for i in edge.vertices[index]]
        return p2 - p1

    root_edge_vector = get_vector_from_edge(root_edge, root_edge.index)
    edge_border_indices = cmds.polySelect(
        root_edge.dagpath,
        edgeBorder=root_edge.index,
        noSelection=True
    )
    border_edge = root_edge.new().add(edge_border_indices)
    edges_to_select = root_edge.new()
    for idx in border_edge:
        border_edge_vector = get_vector_from_edge(border_edge, idx)
        if root_edge_vector.isParallel(border_edge_vector, tolerance):
            edges_to_select.add(idx)

    connected = edges_to_select.get_connected_components()
    for e in connected:
        if root_edge.index in e:
            if root_edge in mampy.complist():
                cmds.select(e.cmdslist(), d=True)
            else:
                cmds.select(e.cmdslist(), add=True)


def select_deselect_edge_lists(root_edge, loop=True):
    kw = {'edgeLoop' if loop else 'edgeRing': root_edge.index}
    if root_edge in mampy.complist():
        kw.update({'deselect': True})
    else:
        kw.update({'add': True})
    cmds.polySelect(root_edge.dagpath, **kw)


def select_deselect_surrounded(root_comp):
    selected = mampy.complist()
    if not selected:
        cmds.selecet(root_comp.get_complete().cmdslist(), add=True)
    else:
        for comp in selected:
            # Find correct dagpath to work on
            if not root_comp.dagpath == comp.dagpath:
                continue

            if comp.is_complete():
                cmds.select(comp.cmdslist(), d=True)
            else:
                connected = list(comp.get_connected_components())
                connected_unselected = list(comp.toggle().get_connected_components())

                if any(root_comp.index in c for c in connected):
                    kw = {'deselect': True}
                    iterable = connected
                elif any(root_comp.index in c for c in connected_unselected):
                    kw = {'add': True}
                    iterable = connected_unselected

                for c in iterable:
                    if root_comp.index in c:
                        cmds.select(c.cmdslist(), **kw)


@undoable()
@repeatable
def select_deselect_isolated_components(loop=True, tolerance=0.35):
    """Clear mesh or loop under mouse."""
    preselect = mampy.complist(preSelectHilite=True)
    if not preselect:
        raise NothingSelected()

    preselect_component = preselect.pop()
    if preselect_component.type == api.MFn.kMeshEdgeComponent:
        if not loop:
            select_deselect_edge_lists(preselect_component, loop)
        elif preselect_component.is_border(preselect_component.index):
            select_deselect_border_edge(preselect_component, tolerance)
        else:
            select_deselect_edge_lists(preselect_component, loop)
    else:
        select_deselect_surrounded(preselect_component)


@undoable()
@repeatable
def toggle_mesh_under_cursor():
    """Toggle mesh object under cursor."""
    preselect = mampy.complist(preSelectHilite=True)
    if not preselect:
        under_cursor_mesh = get_object_under_cursor()
        if under_cursor_mesh is None:
            return
        node = Node(under_cursor_mesh)
        if cmds.selectMode(q=True, component=True):
            cmds.hilite(str(node.transform))
        else:
            cmds.select(str(node), toggle=True)
    else:
        node = preselect.pop().mdag
        if node.transform in mampy.daglist(hl=True):
            cmds.hilite(str(node.transform), unHilite=True)


@undoable()
def deselect_all_but():
    preselect = mampy.complist(preSelectHilite=True)
    obj = get_object_under_cursor()
    if not obj:
        return

    cmds.select(obj, r=True)
    if not preselect:
        return
    else:
        cmds.hilite(obj, toggle=True)


@undoable()
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

    selected, converted = mampy.complist(), ComponentList()
    if not selected:
        raise NothingSelected()

    for comp in selected:
        if comp.type == convert_mode:
            continue
        converted.append(getattr(comp, convert_mode.function)(**convert_arguments))

    set_selection_mask(comptype)
    cmds.select(converted.cmdslist())


@undoable()
@repeatable
def flood():
    """Get contiguous components from current selection."""
    selected = mampy.complist()
    if not selected:
        raise NothingSelected()

    flood = ComponentList()
    for comp in selected:
        if comp.type == MFn.kMeshMapComponent:
            iter_ = comp.map_shells
        else:
            iter_ = comp.mesh_shells
        flood.extend(iter_.itervalues())
    cmds.select(flood.cmdslist())


@undoable()
@repeatable
def inbetween():
    """Select components between the last two selections."""
    # TODO: refactor and finish.
    ordered_selection = mampy.complist(os=True)

    if not len(ordered_selection) % 2 == 0:
        comp1, comp2 = ordered_selection[-2:]
    else:
        for comp in ordered_selection:
            cmds.polySelect(comp.cmdslist(), q=True, loop=True)


    # comptype = slist.itercomps().next().type
    # indices = [c.index for c in slist.itercomps()]

    # if (comptype in [
    #         api.MFn.kMeshPolygonComponent,
    #         api.MFn.kMeshEdgeComponent,
    #         api.MFn.kMeshVertComponent]):
    #     # check if a edge ring can be selected.
    #     if (comptype == api.MFn.kMeshEdgeComponent and
    #             cmds.polySelect(q=True, edgeRingPath=indices)):
    #         inbetween = cmds.polySelect(q=True, ass=True, edgeRingPath=indices)
    #     else:
    #         inbetween = cmds.polySelectSp(list(slist), q=True, loop=True)
    # elif comptype == api.MFn.kMeshMapComponent:
    #     path = cmds.polySelect(q=True, ass=True, shortestEdgePathUV=indices)
    #     inbetween = cmds.polyListComponentConversion(path, tuv=True)

    # cmds.select(inbetween, add=True)


@undoable()
@repeatable
def poly_invert(shell=False):
    """
    Invert selection.

    If shell is active but there are no selections, script assumes we
    want a full invert.

    .. note:: If current selection mask is *object* and there are no
        selections there is no way that I know of to find out the active
        component type.
    """
    # To find out how we want to operate on the objects we walk through
    # the possible outcomes leaving the object list at last.
    modes = [mampy.complist(), mampy.daglist(hl=True), mampy.daglist()]
    for mode, selected in enumerate(modes):
        if not selected:
            continue
        break

    if mode == 2:
        if not selected:
            cmds.select(mampy.daglist(visible=True, assemblies=True).cmdslist())
        else:
            cmds.select(selected.cmdslist(), toggle=True)
    if mode == 1:
        for mask in get_active_flags_in_mask(object=False):
            try:
                active_mask = {
                    'facet': MFn.kMeshPolygonComponent,
                    'edge': MFn.kMeshEdgeComponent,
                    'vertex': MFn.kMeshVertComponent,
                    'polymeshUV': MFn.kMeshMapComponent,
                }[mask]; break
            except KeyError:
                continue
        for dag in selected:
            component = SingleIndexComponent.create(dag.dagpath, active_mask)
            cmds.select(component.get_complete().cmdslist(), toggle=True)
    if mode == 0:
        selection_list = ComponentList()
        for comp in selected:
            if shell:
                for mesh in comp.mesh_shells.itervalues():
                    selection_list.append(mesh)
            else:
                selection_list.append(comp.get_complete())
        cmds.select(selection_list.cmdslist(), toggle=True)


@undoable()
@repeatable
def nonquads(ngons=True, query=False):
    """
    Select all nonquads from an object.
    """
    type_ = 3 if ngons else 1

    if query:
        selected = mampy.daglist()

    cmds.selectMode(component=True)
    cmds.selectType(facet=True)

    cmds.polySelectConstraint(mode=3, t=0x0008, size=type_)
    cmds.polySelectConstraint(disable=True)
    ngons = mampy.daglist()

    if query:
        cmds.select(selected.cmdslist())
        return ngons
    sys.stdout.write(str(len(ngons)) + ' N-Gon(s) Selected.\n')


@undoable()
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
    pass
