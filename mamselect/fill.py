import logging

import shiboken
from PySide.QtCore import QObject, QEvent, Slot, QPoint, Signal
from PySide.QtGui import QWidget, QApplication

from maya import cmds
import maya.OpenMayaUI as apiUI

import mampy
from mampy.dgcomps import MeshPolygon
from mampy.computils import get_shells


logger = logging.getLogger(__file__)
logger.setLevel(logging.DEBUG)


UVSET_NAME = 'mamtools_fill_uvset'


def get_maya_main_window():
    """Get the main Maya window as a QtGui.QMainWindow instance."""
    ptr = apiUI.MQtUtil.mainWindow()
    if ptr is not None:
        return shiboken.wrapInstance(long(ptr), QWidget)


def get_nice_name(widget):
    """Recursive search for a widgets nice name."""
    if widget.objectName().startswith('formLayouts'):
        return get_nice_name(widget.parent())
    return widget.objectName()


class MouseEventFilter(QObject):

    moved = Signal()

    def __init__(self, *args):
        super(MouseEventFilter, self).__init__(*args)
        self.active = False
        self.watched = dict()
        self.pos = QPoint(0, 0)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseMove:
            self.moved.emit()
            # self.pos = event.pos()
        return False

    @Slot(QWidget, QWidget)
    def update_event_list(self, old_widget, new_widget):
        """Add MouseEventEater as event filter on widget if in mouse interactable.

        Implement custom mouse interactables in quickkeys_mouse_interactables.
        """
        if new_widget is None or old_widget is new_widget:
            return

        name = get_nice_name(new_widget)  # ;logger.debug(name)
        if name in self.watched:
            return
        else:
            model = apiUI.M3dView()
            apiUI.M3dView.getM3dViewFromModelPanel(name, model)
            widget = shiboken.wrapInstance(long(model.widget()), QWidget)

        if widget is None:
            return

        widget.installEventFilter(self)
        self.watched[name] = widget
        logger.debug(self.watched)

    def remove_filters(self):
        """Remove event filter from watches widgets."""
        for widget in self.watched.itervalues():
            widget.removeEventFilter(self)

    def install_filters(self):
        """Install event filters on watched widgets."""
        for widget in self.watched.itervalues():
            widget.installEventFilter(self)

    def activate(self):
        QApplication.instance().focusChanged.connect(self.update_event_list)
        self.install_filters()
        self.active = True

    def deactivate(self):
        QApplication.instance().focusChanged.disconnect(self.update_event_list)
        self.remove_filters()
        self.active = False


class fill(object):

    def __init__(self):
        # self.mouse_event = MouseEventFilter()
        # self.mouse_event.moved.connect(self.on_move)

        self._slist = None
        self._dagpath = None
        self._active_shell = None
        self._scriptjob = None

        self.shells = list()
        self.active_shell = None

        self.setup()

    # @Slot()
    # def on_move(self):
    #     selection = mampy.ls(preSelectHilite=True).itercomps().next()
    #     for each in self.shells:
    #         if selection not in each:
    #             continue
    #         if self.active_shell is None or not each == self.active_shell:
    #             self.active_shell = each
    #         cmds.select(list(each), r=True)
    #         break

    @property
    def slist(self):
        if self._slist is None:
            self._slist = mampy.selected()
            if not self._slist and not self._slist.is_edge():
                raise TypeError('Select a closed edge loop.')
        return self._slist

    @property
    def dagpath(self):
        if self._dagpath is None:
            self._dagpath = self.slist.itercomps().next().dagpath
        return self._dagpath

    def setup(self):
        # self.mouse_event.activate()

        cmds.undoInfo(openChunk=True)
        self.create_temp_polygon_projection()
        self.set_selection_mask_and_poly_constrain()
        self.shells = [shell.to_face() for shell in get_shells()]
        cmds.select(list(self.slist))
        self.setup_scriptjob_for_next_selection()

    def create_temp_polygon_projection(self):
        """Project object and cut up selection."""
        faces = MeshPolygon.create(self.dagpath).get_complete()
        cmds.polyProjection(
            list(faces),
            type='planar',
            uvSetName=UVSET_NAME,
            createNewMap=True,
            mapDirection='c',
            insertBeforeDeformers=True,
        )
        cmds.polyUVSet(self.dagpath, currentUVSet=True, uvSet=UVSET_NAME)
        cmds.polyMapCut(list(self.slist))

    def set_selection_mask_and_poly_constrain(self):
        mask = mampy.get_active_mask()
        mask.set_mode(mask.kSelectComponentMode)
        mask.set_mask(mask.kSelectMeshFaces)
        cmds.select(cl=True)
        cmds.undoInfo(closeChunk=True)

    def setup_scriptjob_for_next_selection(self):
        logger.debug('creating scriptjob...')
        if self._scriptjob is None:
            self._scriptjob = cmds.scriptJob(
                event=['SelectionChanged', self.tear_down],
                runOnce=True,
            )

    def tear_down(self):
        # self.mouse_event.deactivate()
        logger.debug('tearing down...')
        selection = mampy.ordered_selection(0, 1).pop()
        for each in self.shells:
            if selection not in each:
                continue
            cmds.select(list(each), r=True)

        cmds.polyUVSet(self.dagpath, delete=True, uvSet=UVSET_NAME)


if __name__ == '__main__':
    fill()

