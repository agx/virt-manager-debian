# Copyright (C) 2006, 2013 Red Hat, Inc.
# Copyright (C) 2006 Daniel P. Berrange <berrange@redhat.com>
#
# This work is licensed under the GNU GPLv2 or later.
# See the COPYING file in the top-level directory.

# pylint: disable=wrong-import-order,ungrouped-imports
import gi
from gi.repository import Gdk
from gi.repository import Gtk

from virtinst import log

# We can use either 2.91 or 2.90. This is just to silence runtime warnings
try:
    gi.require_version("Vte", "2.91")
    log.debug("Using VTE API 2.91")
except ValueError:
    gi.require_version("Vte", "2.90")
    log.debug("Using VTE API 2.90")
from gi.repository import Vte

import libvirt

from ..baseclass import vmmGObject


class ConsoleConnection(vmmGObject):
    def __init__(self, vm):
        vmmGObject.__init__(self)

        self.vm = vm
        self.conn = vm.conn

        self.stream = None

        self.streamToTerminal = b""
        self.terminalToStream = ""

    def _cleanup(self):
        self.close()

        self.vm = None
        self.conn = None

    def _event_on_stream(self, stream, events, opaque):
        ignore = stream
        terminal = opaque

        if (events & libvirt.VIR_EVENT_HANDLE_ERROR or
            events & libvirt.VIR_EVENT_HANDLE_HANGUP):
            log.debug("Received stream ERROR/HANGUP, closing console")
            self.close()
            return

        if events & libvirt.VIR_EVENT_HANDLE_READABLE:
            try:
                got = self.stream.recv(1024 * 100)
            except Exception:
                log.exception("Error receiving stream data")
                self.close()
                return

            if got == -2:
                # This is basically EAGAIN
                return
            if len(got) == 0:
                log.debug("Received EOF from stream, closing")
                self.close()
                return

            queued_text = bool(self.streamToTerminal)
            self.streamToTerminal += got
            if not queued_text:
                self.idle_add(self.display_data, terminal)

        if (events & libvirt.VIR_EVENT_HANDLE_WRITABLE and
            self.terminalToStream):

            try:
                done = self.stream.send(self.terminalToStream.encode())
            except Exception:
                log.exception("Error sending stream data")
                self.close()
                return

            if done == -2:
                # This is basically EAGAIN
                return

            self.terminalToStream = self.terminalToStream[done:]

        if not self.terminalToStream:
            self.stream.eventUpdateCallback(libvirt.VIR_STREAM_EVENT_READABLE |
                                            libvirt.VIR_STREAM_EVENT_ERROR |
                                            libvirt.VIR_STREAM_EVENT_HANGUP)


    def is_open(self):
        return self.stream is not None

    def open(self, dev, terminal):
        if self.stream:
            self.close()

        name = dev and dev.alias.name or None
        log.debug("Opening console stream for dev=%s alias=%s",
                      dev, name)
        # libxl doesn't set aliases, their open_console just defaults to
        # opening the first console device, so don't force prescence of
        # an alias

        stream = self.conn.get_backend().newStream(libvirt.VIR_STREAM_NONBLOCK)
        self.vm.open_console(name, stream)
        self.stream = stream

        self.stream.eventAddCallback((libvirt.VIR_STREAM_EVENT_READABLE |
                                      libvirt.VIR_STREAM_EVENT_ERROR |
                                      libvirt.VIR_STREAM_EVENT_HANGUP),
                                     self._event_on_stream,
                                     terminal)

    def close(self):
        if self.stream:
            try:
                self.stream.eventRemoveCallback()
            except Exception:
                log.exception("Error removing stream callback")
            try:
                self.stream.finish()
            except Exception:
                log.exception("Error finishing stream")

        self.stream = None

    def send_data(self, src, text, length, terminal):
        """
        Callback when data has been entered into VTE terminal
        """
        ignore = src
        ignore = length
        ignore = terminal

        if self.stream is None:
            return

        self.terminalToStream += text
        if self.terminalToStream:
            self.stream.eventUpdateCallback(libvirt.VIR_STREAM_EVENT_READABLE |
                                            libvirt.VIR_STREAM_EVENT_WRITABLE |
                                            libvirt.VIR_STREAM_EVENT_ERROR |
                                            libvirt.VIR_STREAM_EVENT_HANGUP)

    def display_data(self, terminal):
        if not self.streamToTerminal:
            return

        terminal.feed(self.streamToTerminal)
        self.streamToTerminal = b""


class vmmSerialConsole(vmmGObject):

    @staticmethod
    def can_connect(vm, dev):
        """
        Check if we think we can actually open passed console/serial dev
        """
        usable_types = ["pty"]
        ctype = dev.type

        err = ""

        if not vm.is_active():
            err = _("Serial console not available for inactive guest")
        elif ctype not in usable_types:
            err = (_("Console for device type '%s' is not supported") % ctype)

        return err

    def __init__(self, vm, target_port, name):
        vmmGObject.__init__(self)

        self.vm = vm
        self.target_port = target_port
        self.name = name
        self.lastpath = None

        self.console = ConsoleConnection(self.vm)

        self.serial_popup = None
        self.serial_copy = None
        self.serial_paste = None
        self.serial_close = None
        self.init_popup()

        self.terminal = None
        self.init_terminal()

        self.box = None
        self.error_label = None
        self.init_ui()

        self.vm.connect("state-changed", self.vm_status_changed)

    def init_terminal(self):
        self.terminal = Vte.Terminal()
        self.terminal.set_scrollback_lines(1000)
        self.terminal.set_audible_bell(False)
        self.terminal.get_accessible().set_name("Serial Terminal")

        self.terminal.connect("button-press-event", self.show_serial_rcpopup)
        self.terminal.connect("commit", self.console.send_data, self.terminal)
        self.terminal.show()

    def init_popup(self):
        self.serial_popup = Gtk.Menu()

        self.serial_copy = Gtk.ImageMenuItem.new_from_stock(Gtk.STOCK_COPY,
                                                            None)
        self.serial_copy.connect("activate", self.serial_copy_text)
        self.serial_popup.add(self.serial_copy)

        self.serial_paste = Gtk.ImageMenuItem.new_from_stock(Gtk.STOCK_PASTE,
                                                             None)
        self.serial_paste.connect("activate", self.serial_paste_text)
        self.serial_popup.add(self.serial_paste)

    def init_ui(self):
        self.box = Gtk.Notebook()
        self.box.set_show_tabs(False)
        self.box.set_show_border(False)

        align = Gtk.Alignment()
        align.set_padding(2, 2, 2, 2)
        evbox = Gtk.EventBox()
        evbox.modify_bg(Gtk.StateType.NORMAL, Gdk.Color(0, 0, 0))
        terminalbox = Gtk.HBox()
        scrollbar = Gtk.VScrollbar()
        self.error_label = Gtk.Label()
        self.error_label.set_width_chars(40)
        self.error_label.set_line_wrap(True)

        if self.terminal:
            scrollbar.set_adjustment(self.terminal.get_vadjustment())
            align.add(self.terminal)

        evbox.add(align)
        terminalbox.pack_start(evbox, True, True, 0)
        terminalbox.pack_start(scrollbar, False, False, 0)

        self.box.append_page(terminalbox, Gtk.Label(""))
        self.box.append_page(self.error_label, Gtk.Label(""))
        self.box.show_all()

        scrollbar.hide()
        scrollbar.get_adjustment().connect(
            "changed", self._scrollbar_adjustment_changed, scrollbar)

    def _scrollbar_adjustment_changed(self, adjustment, scrollbar):
        scrollbar.set_visible(
            adjustment.get_upper() > adjustment.get_page_size())

    def _cleanup(self):
        self.console.cleanup()
        self.console = None

        self.vm = None
        self.terminal = None
        self.box = None

    def close(self):
        if self.console:
            self.console.close()

    def show_error(self, msg):
        self.error_label.set_markup("<b>%s</b>" % msg)
        self.box.set_current_page(1)

    def open_console(self):
        try:
            if not self.console.is_open():
                self.console.open(self.lookup_dev(), self.terminal)
            self.box.set_current_page(0)
            return True
        except Exception as e:
            log.exception("Error opening serial console")
            self.show_error(_("Error connecting to text console: %s") % e)
            try:
                self.console.close()
            except Exception:
                pass

        return False

    def vm_status_changed(self, vm):
        if vm.status() in [libvirt.VIR_DOMAIN_RUNNING]:
            self.open_console()
        else:
            self.console.close()

    def lookup_dev(self):
        devs = self.vm.get_serialcon_devices()
        for dev in devs:
            port = dev.get_xml_idx()
            path = dev.source.path

            if port == self.target_port:
                if path != self.lastpath:
                    log.debug("Serial console '%s' path changed to %s",
                                  self.target_port, path)
                self.lastpath = path
                return dev

        log.debug("No devices found for serial target port '%s'",
                      self.target_port)
        self.lastpath = None
        return None

    #######################
    # Popup menu handling #
    #######################

    def show_serial_rcpopup(self, src, event):
        if event.button != 3:
            return

        self.serial_popup.show_all()

        if src.get_has_selection():
            self.serial_copy.set_sensitive(True)
        else:
            self.serial_copy.set_sensitive(False)
        self.serial_popup.popup_at_pointer(event)

    def serial_copy_text(self, src_ignore):
        self.terminal.copy_clipboard()

    def serial_paste_text(self, src_ignore):
        self.terminal.paste_clipboard()
