"""
Improvement to Mayas isolate select tool.

I wanted more control when isolating and realized that I was re isolating objects
a lot after having initially isolated an object. A lot of functionality was not
there when this was created, such as auto adding new objects on creation, meaning
some functionality is obsolete.

To note, this isolating system works only on objects. This means you can't isolate
components. Although that might be desirable at times from experience it's
confusing since mesh operations will still apply to components outside of view.

# TODO: Refactor to fit with new mampy standard.
"""
import logging

from PySide.QtCore import QTimer

from maya import cmds
from maya.OpenMaya import MEventMessage

import mampy

logger = logging.getLogger(__name__)


TIMER = QTimer()
TIMER.setSingleShot(True)
TIMER_SET = False
SELECT_CHANGE_EVENT = None


def is_component(selected):
    return any(i.is_valid() for i in selected.itercomps())


def get_selected_transforms(selection):
    return [str(i.get_transform())[1:] for i in selection.iterdags()]


def get_clean_dagpaths(dagpaths):
    return [str(i)[1:] for i in dagpaths.iterdags()]


def get_clean_list_object(objects):
    if is_component(objects):
        return get_selected_transforms(objects)
    return get_clean_dagpaths(objects)


def get_selected_objects():
    return get_clean_list_object(mampy.selected())


def get_isolate_set_name():
    return cmds.isolateSelect(get_active_panel(), q=True, viewObjects=True)


def isolate_new_objects():
    objs = get_selected_objects()
    logger.debug('changed selection: {}'.format(objs))
    if objs:
        try:
            cmds.sets(objs, include=get_isolate_set_name())
        except TypeError:
            pass


def get_active_panel():
    return cmds.getPanel(withFocus=True)


def is_isolated():
    return cmds.isolateSelect(get_active_panel(), q=True, state=True)


def set_isolate_set(selection):
    set_name = get_isolate_set_name()

    # Unhilite
    isoset = cmds.ls(hl=True)
    for obj in isoset:
        if obj in selection:
            isoset.remove(obj)
    cmds.hilite(isoset, toggle=True)

    if not set_name:
        for i in selection:
            cmds.isolateSelect(get_active_panel(), addDagObject=i)
        return

    cmds.sets(clear=set_name)
    cmds.sets(selection, include=set_name)


def set_isolate_selected_off_or_update():
    global SELECT_CHANGE_EVENT
    isoset = cmds.sets(get_isolate_set_name(), q=True)
    selset = get_selected_objects()

    if isoset:
        if set(isoset) == set(selset) or not selset:
            try:
                MEventMessage.removeCallback(SELECT_CHANGE_EVENT)
                SELECT_CHANGE_EVENT = None
            except RuntimeError:
                pass
            cmds.isolateSelect(get_active_panel(), state=False)
        else:
            set_isolate_set(selset)


def on_selection_changed(*args):
    if TIMER.isActive():
        TIMER.stop()

    if not get_selected_objects():
        return
    TIMER.start(50)


def create_select_change_event():
    global SELECT_CHANGE_EVENT
    if SELECT_CHANGE_EVENT:
        return True
    SELECT_CHANGE_EVENT = MEventMessage.addEventCallback('SelectionChanged',
                                                         on_selection_changed)


def set_isolate_selected_on():
    sel = get_selected_objects()
    if not sel:
        return logger.warn('Nothing selected, ignoring isolate.')

    cmds.isolateSelect(get_active_panel(), state=True)
    set_isolate_set(sel)
    create_select_change_event()


def toggle():
    global TIMER_SET
    if not TIMER_SET:
        TIMER.timeout.connect(isolate_new_objects)
        TIMER_SET = True

    if not is_isolated():
        return set_isolate_selected_on()
    set_isolate_selected_off_or_update()


if __name__ == '__main__':
    toggle()
