"""
This module contains functionality to let you toggle on or off the smooth mesh
in Maya.

If you want to quickly view how the mesh will sub divide this will work great,
you can decide to display only selected or change the display of all mesh objects;
even the subdivision levels.
"""
from functools import partial

from maya import cmds
from maya.api.OpenMaya import MFn

import mampy
from mampy.core.selectionlist import DagpathList


def find_matching_in_hilited(objects):
    hilited = mampy.daglist(hl=True, dag=True, type='mesh')
    if not hilited:
        return objects

    for obj in objects:
        parent = str(obj).lstrip('|').split('|')[0]
        for child in hilited:
            if child == obj:
                continue
            child_name = str(child).lstrip('|').split('|')[0]
            if parent == child_name:
                objects.append(child)
    return objects


Selected, Hierarchy, All = (0, 1, 2)
def get_mesh_objects(mode):
    objects = {
        All: partial(mampy.daglist, type='mesh'),
        Hierarchy: partial(mampy.daglist, sl=True, dag=True, type='mesh'),
        Selected: partial(mampy.daglist, sl=True),
    }[mode]()
    if mode == All:
        return objects
    elif mode == Hierarchy and not objects:
        objects = mampy.daglist()

    # Make subd toggle work when in component mode.
    if mode == Hierarchy:
        objects = find_matching_in_hilited(objects)
    # Add hilited objects to existing list and sort out meshes.
    # objects.extend(other)
    mesh_objects = DagpathList()
    for dag in objects:
        if dag.type == MFn.kMesh:
            mesh_objects.append(dag)
        else:
            if dag.shape.type == MFn.kMesh:
                mesh_objects.append(dag.shape)
    return mesh_objects


def toggle(hierarchy=False):
    meshes = get_mesh_objects(Hierarchy if hierarchy else Selected)
    for mesh in meshes:
        try:
            state = cmds.displaySmoothness(str(mesh), q=True, po=True).pop()
        except AttributeError:
            pass
        cmds.displaySmoothness(str(mesh), po=0 if state == 3 else 3)


def toggle_all(state):
    meshes = get_mesh_objects(All)
    for mesh in meshes:
        cmds.displaySmoothness(str(mesh), po=3 if state else 0)


def set_smooth_level(level=1, all=True, hierarchy=False):
    if all:
        meshes = get_mesh_objects(All)
    else:
        meshes = get_mesh_objects(Hierarchy if hierarchy else Selected)
    for mesh in meshes.iterdags():
        mesh.attr['smoothLevel'] = mesh.attr['smoothLevel'] + level
