#
# Copyright (C) 2012 Red Hat, Inc.
# Copyright (C) 2012 Cole Robinson <crobinso@redhat.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA 02110-1301 USA.
#

# pylint: disable=E0611
from gi.repository import Gio
from gi.repository import Gtk
# pylint: enable=E0611

import logging
import time
import traceback

from virtManager.asyncjob import vmmAsyncJob

#############################
# PackageKit lookup helpers #
#############################


def check_packagekit(errbox, packages, ishv):
    """
    Returns None when we determine nothing useful.
    Returns (success, did we just install libvirt) otherwise.
    """
    if not packages:
        logging.debug("No PackageKit packages to search for.")
        return

    logging.debug("Asking PackageKit what's installed locally.")
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        pk_control = Gio.DBusProxy.new_sync(bus, 0, None,
                                "org.freedesktop.PackageKit",
                                "/org/freedesktop/PackageKit",
                                "org.freedesktop.PackageKit", None)
    except Exception:
        logging.exception("Couldn't connect to packagekit")
        return

    if ishv:
        msg = _("Searching for available hypervisors...")
    else:
        msg = _("Checking for installed package '%s'") % packages[0]

    cancellable = Gio.Cancellable()
    progWin = vmmAsyncJob(_do_async_search,
                          [bus, pk_control, packages, cancellable], msg, msg,
                          errbox.get_parent(), async=False,
                          cancel_cb=[_cancel_search, cancellable])
    error, ignore = progWin.run()
    if error:
        return

    found = progWin.get_extra_data()

    not_found = [x for x in packages if x not in found]
    logging.debug("Missing packages: %s", not_found)

    do_install = not_found
    if not do_install:
        if not not_found:
            # Got everything we wanted, try to connect
            logging.debug("All packages found locally.")
            return []

        else:
            logging.debug("No packages are available for install.")
            return

    missing = reduce(lambda x, y: x + "\n" + y, do_install, "")
    if ishv:
        msg = (_("The following packages are not installed:\n%s\n\n"
                 "These are required to create KVM guests locally.\n"
                 "Would you like to install them now?") % missing)
        title = _("Packages required for KVM usage")
    else:
        msg = _("The following packages are not installed:\n%s\n\n"
                "Would you like to install them now?" % missing)
        title = _("Recommended package installs")

    ret = errbox.yes_no(title, msg)

    if not ret:
        logging.debug("Package install declined.")
        return

    try:
        packagekit_install(do_install)
    except Exception, e:
        errbox.show_err(_("Error talking to PackageKit: %s") % str(e))
        return

    return do_install


def _cancel_search(asyncjob, cancellable):
    cancellable.cancel()
    asyncjob.job_cancelled = True


def _do_async_search(asyncjob, bus, pk_control, packages, cancellable):
    found = []
    try:
        for name in packages:
            ret_found = packagekit_search(bus, pk_control, name, packages,
                                          cancellable)
            found += ret_found
    except Exception, e:
        if cancellable.is_cancelled():
            logging.debug("Package search cancelled by user")
            asyncjob.set_error("Package search cancelled by user")
        else:
            logging.exception("Error searching for installed packages")
            asyncjob.set_error(str(e), "".join(traceback.format_exc()))

    asyncjob.set_extra_data(found)


def packagekit_install(package_list):
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    pk_control = Gio.DBusProxy.new_sync(bus, 0, None,
                            "org.freedesktop.PackageKit",
                            "/org/freedesktop/PackageKit",
                            "org.freedesktop.PackageKit.Modify", None)

    # Set 2 hour timeout
    timeout = 1000 * 60 * 60 * 2
    logging.debug("Installing packages: %s", package_list)
    pk_control.InstallPackageNames("(uass)", 0,
                                   package_list, "hide-confirm-search",
                                   timeout=timeout)


def packagekit_search(bus, pk_control, package_name, packages, cancellable):
    tid = pk_control.CreateTransaction()
    pk_trans = Gio.DBusProxy.new_sync(bus, 0, None,
                            "org.freedesktop.PackageKit", tid,
                            "org.freedesktop.PackageKit.Transaction",
                            cancellable)

    found = []
    def package(info, package_id, summary):
        ignore = info
        ignore = summary

        found_name = str(package_id.split(";")[0])
        if found_name in packages:
            found.append(found_name)

    def error(code, details):
        raise RuntimeError("PackageKit search failure: %s %s" %
                            (code, details))

    def finished(ignore, runtime_ignore):
        Gtk.main_quit()

    def signal_cb(proxy, sender, signal, args):
        ignore = proxy
        sender = proxy
        if signal == "Finished":
            finished(*args)
        elif signal == "ErrorCode":
            error(*args)
        elif signal == "Package":
            package(*args)

    pk_trans.connect("g-signal", signal_cb)
    pk_trans.SearchNames("(tas)", 2 ** 2, [package_name])

    # Call main() so this function is synchronous
    Gtk.main()

    return found

###################
# Service helpers #
###################


def start_libvirtd():
    """
    Connect to systemd and start libvirtd if required
    """
    logging.debug("Trying to start libvirtd through systemd")
    unitname = "libvirtd.service"

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    except:
        logging.exception("Error getting system bus handle")
        return

    try:
        systemd = Gio.DBusProxy.new_sync(bus, 0, None,
                                 "org.freedesktop.systemd1",
                                 "/org/freedesktop/systemd1",
                                 "org.freedesktop.systemd1.Manager", None)
    except:
        logging.exception("Couldn't connect to systemd")
        return

    try:
        unitpath = systemd.GetUnit("(s)", unitname)
        unit = Gio.DBusProxy.new_sync(bus, 0, None,
                                 "org.freedesktop.systemd1", unitpath,
                                 "org.freedesktop.systemd1.Unit", None)
        state = unit.get_cached_property("ActiveState")

        logging.debug("libvirtd state=%s", state)
        if str(state).lower().strip("'") == "active":
            logging.debug("libvirtd already active, not starting")
            return True
    except:
        logging.exception("Failed to lookup libvirtd status")
        return

    # Connect to system-config-services and offer to start
    try:
        logging.debug("libvirtd not running, asking system-config-services "
                      "to start it")
        scs = Gio.DBusProxy.new_sync(bus, 0, None,
                             "org.fedoraproject.Config.Services",
                             "/org/fedoraproject/Config/Services/systemd1",
                             "org.freedesktop.systemd1.Manager", None)
        scs.StartUnit("(ss)", unitname, "replace")
        time.sleep(2)
        logging.debug("Starting libvirtd appeared to succeed")
        return True
    except:
        logging.exception("Failed to talk to system-config-services")
