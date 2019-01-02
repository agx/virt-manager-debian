# Copyright (C) 2012-2013 Red Hat, Inc.
# Copyright (C) 2012 Cole Robinson <crobinso@redhat.com>
#
# This work is licensed under the GNU GPLv2 or later.
# See the COPYING file in the top-level directory.

import collections
import logging
import os
import re
import time

from gi.repository import GLib
from gi.repository import Gio

import libvirt


def do_we_have_session():
    pid = os.getpid()
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    except Exception:
        logging.exception("Error getting system bus handle")
        return

    # Check systemd
    try:
        manager = Gio.DBusProxy.new_sync(bus, 0, None,
                        "org.freedesktop.login1",
                        "/org/freedesktop/login1",
                        "org.freedesktop.login1.Manager", None)

        ret = manager.GetSessionByPID("(u)", pid)
        logging.debug("Found login1 session=%s", ret)
        return True
    except Exception:
        logging.exception("Couldn't connect to logind")

    return False


def creds_dialog(creds, cbdata):
    """
    Thread safe wrapper for libvirt openAuth user/pass callback
    """
    retipc = []

    def wrapper(fn, creds, cbdata):
        try:
            ret = fn(creds, cbdata)
        except Exception:
            logging.exception("Error from creds dialog")
            ret = -1
        retipc.append(ret)

    GLib.idle_add(wrapper, _creds_dialog_main, creds, cbdata)

    while not retipc:
        time.sleep(.1)

    return retipc[0]


def _creds_dialog_main(creds, cbdata):
    """
    Libvirt openAuth callback for username/password credentials
    """
    _conn = cbdata
    from gi.repository import Gtk

    dialog = Gtk.Dialog(_("Authentication required"), None, 0,
                        (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                         Gtk.STOCK_OK, Gtk.ResponseType.OK))
    dialog.set_resizable(False)
    labels = []
    entrys = []

    dialog.set_border_width(6)
    box = Gtk.Grid()
    box.set_hexpand(False)
    box.set_vexpand(False)
    box.set_row_spacing(6)
    box.set_column_spacing(6)
    box.set_margin_bottom(12)

    def _on_ent_activate(ent):
        idx = entrys.index(ent)
        if idx < len(entrys) - 1:
            entrys[idx + 1].grab_focus()
        else:
            dialog.response(Gtk.ResponseType.OK)

    row = 0
    for cred in creds:
        # Libvirt virConnectCredential
        credtype, prompt, _challenge, _defresult, _result = cred
        noecho = credtype in [
                libvirt.VIR_CRED_PASSPHRASE, libvirt.VIR_CRED_NOECHOPROMPT]
        if not prompt:
            logging.error("No prompt for auth credtype=%s", credtype)
            return -1

        prompt += ": "
        label = Gtk.Label()
        label.set_hexpand(False)
        label.set_halign(Gtk.Align.START)
        label.set_line_wrap(True)
        label.set_max_width_chars(40)
        label.set_text(prompt)
        labels.append(label)

        entry = Gtk.Entry()
        if noecho:
            entry.set_visibility(False)
        entry.set_valign(Gtk.Align.START)
        entry.connect("activate", _on_ent_activate)
        entrys.append(entry)

        box.attach(labels[row], row, row, 1, 1)
        box.attach(entrys[row], row + 1, row, 1, 1)
        row = row + 1

    dialog.get_child().add(box)
    dialog.show_all()
    res = dialog.run()
    dialog.hide()

    if res == Gtk.ResponseType.OK:
        row = 0
        for cred in creds:
            cred[4] = entrys[row].get_text()
            row = row + 1
        ret = 0
    else:
        ret = -1

    dialog.destroy()
    return ret


def connect_error(conn, errmsg, tb, warnconsole):
    """
    Format connection error message
    """
    errmsg = errmsg.strip(" \n")
    tb = tb.strip(" \n")
    hint = ""
    show_errmsg = True

    if conn.is_remote():
        logging.debug("connect_error: conn transport=%s",
            conn.get_uri_transport())
        if re.search(r"nc: .* -- 'U'", tb):
            hint += _("The remote host requires a version of netcat/nc "
                      "which supports the -U option.")
            show_errmsg = False
        elif (conn.get_uri_transport() == "ssh" and
              re.search(r"askpass", tb)):

            hint += _("Configure SSH key access for the remote host, "
                      "or install an SSH askpass package locally.")
            show_errmsg = False
        else:
            hint += _("Verify that the 'libvirtd' daemon is running "
                      "on the remote host.")

    elif conn.is_xen():
        hint += _("Verify that:\n"
                  " - A Xen host kernel was booted\n"
                  " - The Xen service has been started")

    else:
        if warnconsole:
            hint += _("Could not detect a local session: if you are "
                      "running virt-manager over ssh -X or VNC, you "
                      "may not be able to connect to libvirt as a "
                      "regular user. Try running as root.")
            show_errmsg = False
        elif re.search(r"libvirt-sock", tb):
            hint += _("Verify that the 'libvirtd' daemon is running.")
            show_errmsg = False

    msg = _("Unable to connect to libvirt %s." % conn.get_uri())
    if show_errmsg:
        msg += "\n\n%s" % errmsg
    if hint:
        msg += "\n\n%s" % hint

    msg = msg.strip("\n")
    details = msg
    details += "\n\n"
    details += "Libvirt URI is: %s\n\n" % conn.get_uri()
    details += tb

    title = _("Virtual Machine Manager Connection Failure")

    ConnectError = collections.namedtuple("ConnectError",
            ["msg", "details", "title"])
    return ConnectError(msg, details, title)
