"""
Improvement to Mayas isolate select tool.

I wanted more control when isolating and realized that I was re isolating objects
a lot after having initially isolated an object. A lot of functionality was not
there when this was created, such as auto adding new objects on creation, meaning
some functionality is obsolete.

To note, this isolating system works only on objects. This means you can't isolate
components. Although that might be desirable at times from experience it's
confusing since mesh operations will still apply to components outside of view.
"""
import logging

from PySide.QtCore import QTimer

from maya import cmds
from maya.OpenMaya import MEventMessage


logger = logging.getLogger(__name__)


TIMER = QTimer()
TIMER.setSingleShot(True)
TIMER_SET = False
SELECT_CHANGE_EVENT = None


def isolate_new_objects():
    objs = get_selected_objects()
    logger.debug('changed selction: {}'.format(objs))
    if not objs:
        pass
    else:
        cmds.sets(objs, include=get_isolate_set_name())


def get_isolate_state():
    return cmds.isolateSelect(get_active_panel(), q=True, state=True)


def on_selection_changed(*args):
    if TIMER.isActive():
        TIMER.stop()

    if not get_selected_objects():
        return
    TIMER.start(50)


def create_select_change_event():
    global SELECT_CHANGE_EVENT
    event = 'SelectionChanged'
    callback = on_selection_changed
    SELECT_CHANGE_EVENT = MEventMessage.addEventCallback(event, callback)


def get_active_panel():
    return cmds.getPanel(withFocus=True)


def get_isolate_set_name():
    return cmds.isolateSelect(get_active_panel(), q=True, viewObjects=True)


def update_panel():
    try:
        cmds.sets(clear=get_isolate_set_name())
    except TypeError:
        pass
    finally:
        isolate_new_objects()


def set_isolate_selected_on():
    if not get_selected_objects():
        return logger.warn('Nothing selected, ignoring isolate.')
    create_select_change_event()
    cmds.isolateSelect(get_active_panel(), state=True)
    update_panel()


def get_selected_objects():
    return cmds.ls(sl=True) + cmds.ls(hl=True)


def set_isolate_selected_off_or_update():
    isoset = cmds.sets(get_isolate_set_name(), q=True)
    selset = get_selected_objects()

    if isoset:
        if set(isoset) == set(selset) or not selset:
            # Cleanup
            MEventMessage.removeCallback(SELECT_CHANGE_EVENT)
            cmds.isolateSelect(get_active_panel(), state=False)
        else:
            update_panel()


def toggle():
    global TIMER_SET
    # Connect timer object to isolate new function.
    if not TIMER_SET:
        TIMER.timeout.connect(isolate_new_objects)
        TIMER_SET = True

    if not get_isolate_state():
        return set_isolate_selected_on()
    set_isolate_selected_off_or_update()


if __name__ == '__main__':
    toggle()
