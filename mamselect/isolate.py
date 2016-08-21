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
from maya.api.OpenMaya import MFn

import mampy
from mampy.core.selectionlist import DagpathList
from mampy.core.exceptions import NothingSelected

logger = logging.getLogger(__name__)


TIMER = QTimer()
TIMER.setSingleShot(True)
TIMER_SET = False
SELECT_CHANGE_EVENT = None
HIDDEN_CHILDREN = set()


def is_isolated():
    return cmds.isolateSelect(get_active_panel(), q=True, state=True)


def on_selection_changed(*args):
    if TIMER.isActive():
        TIMER.stop()

    if not get_selected_objects():
        return
    TIMER.start(50)


def get_selected_objects():
    return mampy.daglist([dag.transform for dag in mampy.daglist()])


def get_active_panel():
    return cmds.getPanel(withFocus=True)


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


def set_isolate_set(selected):
    set_name = get_isolate_set_name()
    # Trying to hide visible children in hierarchy to get wanted isolate
    # behavior.
    for sel in selected:
        for child in sel.iterchildren():
            if child in selected or not child.type == MFn.kTransform:
                continue
            # Only work on visible children
            if child.attr['visibility']:
                child.attr['visibility'] = False
                HIDDEN_CHILDREN.add(child)

    hilited = DagpathList(
        [dag for dag in mampy.daglist(hl=True) if dag not in selected]
    )
    if hilited:
        cmds.hilite(hilited.cmdslist(), toggle=True)
        # In case the dag object was a child of unhilited object rehilite it.
        for dag in selected:
            cmds.hilite(str(dag))

    if not set_name:
        for dag in selected:
            cmds.isolateSelect(get_active_panel(), addDagObject=str(dag))
        return

    cmds.sets(clear=set_name)
    cmds.sets(selected.cmdslist(), include=set_name)


def create_select_change_event():
    global SELECT_CHANGE_EVENT
    if SELECT_CHANGE_EVENT:
        return True
    SELECT_CHANGE_EVENT = MEventMessage.addEventCallback('SelectionChanged',
                                                         on_selection_changed)


def set_isolate_selected_on():
    selected = get_selected_objects()
    if not selected:
        raise NothingSelected()

    cmds.isolateSelect(get_active_panel(), state=True)
    set_isolate_set(selected)
    create_select_change_event()


def set_isolate_selected_off_or_update():
    global SELECT_CHANGE_EVENT
    isoset = mampy.daglist(cmds.sets(get_isolate_set_name(), q=True))
    selset = get_selected_objects()

    if isoset:
        if isoset == selset or not selset:
            try:
                MEventMessage.removeCallback(SELECT_CHANGE_EVENT)
                SELECT_CHANGE_EVENT = None
            except RuntimeError:
                pass
            cmds.isolateSelect(get_active_panel(), state=False)
            # Show hidden children again and clear HIDDEN_CHILDREN list to
            # avoid uncertain clashes.
            for child in HIDDEN_CHILDREN:
                child.attr['visibility'] = True
            HIDDEN_CHILDREN.clear()
        else:
            set_isolate_set(selset)


def toggle():
    global TIMER_SET
    if not TIMER_SET:
        TIMER.timeout.connect(isolate_new_objects)
        TIMER_SET = True

    if not is_isolated():
        set_isolate_selected_on(); return
    set_isolate_selected_off_or_update()
