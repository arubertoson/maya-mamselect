"""
This module contains functionality to let you toggle on or off the smooth mesh
in Maya.

If you want to quickly view how the mesh will sub divide this will work great,
you can decide to display only selected or change the display of all mesh objects;
even the subdivision levels.
"""
from functools import partial

import mampy
from mampy.dgcontainers import SelectionList
from maya import cmds


def get_shape_from_object(objects):
    selected = SelectionList()
    for mesh in objects.iterdags():
        shape = mesh.get_shape()
        if shape is None:
            continue
        selected.append(shape)
    return selected


def merge_with_hilited(objects):
    hilited = mampy.ls(hl=True, dag=True, type='mesh')
    for h in hilited:
        if h in objects:
            continue
        objects.append(h)
    return objects


def get_mesh_objects(mode):
    objects = {
        'all': partial(mampy.ls, type='mesh'),
        'hierarchy': partial(mampy.ls, sl=True, dag=True, type='mesh'),
        'selected': partial(mampy.ls, sl=True),
    }[mode]()
    if mode == 'all':
        return objects

    # Get shape nodes from selected.
    if mode == 'selected':
        objects = get_shape_from_object(objects)
    return merge_with_hilited(objects)


def toggle(hierarchy=False):
    meshes = get_mesh_objects('hierarchy' if hierarchy else 'selected')
    for mesh in meshes:
        try:
            state = cmds.displaySmoothness(str(mesh), q=True, po=True).pop()
        except AttributeError:
            pass
        cmds.displaySmoothness(str(mesh), po=0 if state == 3 else 3)


def toggle_all(state):
    meshes = get_mesh_objects('all')
    for mesh in meshes:
        cmds.displaySmoothness(str(mesh), po=3 if state else 0)


def set_smooth_level(level=1, all=True, hierarchy=False):
    if all:
        meshes = get_mesh_objects('all')
    else:
        meshes = get_mesh_objects('hierarchy' if hierarchy else 'hierarchy')
    for mesh in meshes.iterdags():
        mesh['smoothLevel'] = mesh['smoothLevel'] + level


if __name__ == '__main__':
    set_smooth_level(-1)
