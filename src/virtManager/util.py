#
# Copyright (C) 2008 Red Hat, Inc.
# Copyright (C) 2008 Cole Robinson <crobinso@redhat.com>
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

import gtk
import gobject

import libvirt
import libxml2

import logging
import os.path

import virtManager
import virtinst

DEFAULT_POOL_NAME = "default"
DEFAULT_POOL_PATH = "/var/lib/libvirt/images"

def build_default_pool(conn):
    """
    Helper to build the 'default' storage pool
    """
    # FIXME: This should use config.get_default_image_path ?

    if not virtinst.util.is_storage_capable(conn):
        # VirtualDisk will raise an error for us
        return

    pool = None
    try:
        pool = conn.storagePoolLookupByName(DEFAULT_POOL_NAME)
    except libvirt.libvirtError:
        pass

    if pool:
        return

    try:
        logging.debug("Attempting to build default pool with target '%s'" %
                      DEFAULT_POOL_PATH)
        defpool = virtinst.Storage.DirectoryPool(conn=conn,
                                                 name=DEFAULT_POOL_NAME,
                                                 target_path=DEFAULT_POOL_PATH)
        newpool = defpool.install(build=True, create=True)
        newpool.setAutostart(True)
    except Exception, e:
        raise RuntimeError(_("Couldn't create default storage pool '%s': %s") %
                             (DEFAULT_POOL_PATH, str(e)))

def get_ideal_path_info(conn, config, name):
    path = get_default_dir(conn, config)
    suffix = ".img"
    return (path, name, suffix)

def get_ideal_path(conn, config, name):
    target, name, suffix = get_ideal_path_info(conn, config, name)
    return os.path.join(target, name) + suffix

def get_default_pool(conn):
    pool = None
    for uuid in conn.list_pool_uuids():
        p = conn.get_pool(uuid)
        if p.get_name() == DEFAULT_POOL_NAME:
            pool = p

    return pool

def get_default_dir(conn, config):
    pool = get_default_pool(conn)

    if pool:
        return pool.get_target_path()
    else:
        return config.get_default_image_dir(conn)

def get_default_path(conn, config, name):
    pool = get_default_pool(conn)

    default_dir = get_default_dir(conn, config)

    if not pool:
        # Use old generating method
        origf = os.path.join(default_dir, name + ".img")
        f = origf

        n = 1
        while os.path.exists(f) and n < 100:
            f = os.path.join(default_dir, name +
                             "-" + str(n) + ".img")
            n += 1

        if os.path.exists(f):
            f = origf

        path = f
    else:
        target, ignore, suffix = get_ideal_path_info(conn, config, name)

        path = virtinst.Storage.StorageVolume.find_free_name(name,
                        pool_object=pool.pool, suffix=suffix)

        path = os.path.join(target, path)

    return path


def tooltip_wrapper(obj, txt, func="set_tooltip_text"):
    # Catch & ignore errors - set_tooltip_* is in gtk >= 2.12
    # and we can easily work with lower versions
    try:
        funcptr = getattr(obj, func)
        funcptr(txt)
    except:
        ver = gtk.gtk_version
        if ver[0] >= 2 and ver[1] >= 12:
            logging.exception("Couldn't set tooltip.")

def xml_parse_wrapper(xml, parse_func, *args, **kwargs):
    """
    Parse the passed xml string into an xpath context, which is passed
    to parse_func, along with any extra arguments.
    """

    doc = None
    ctx = None
    ret = None
    try:
        doc = libxml2.parseDoc(xml)
        ctx = doc.xpathNewContext()
        ret = parse_func(doc, ctx, *args, **kwargs)
    finally:
        if ctx != None:
            ctx.xpathFreeContext()
        if doc != None:
            doc.freeDoc()
    return ret


def browse_local(parent, dialog_name, config, conn, start_folder=None,
                 _type=None, dialog_type=gtk.FILE_CHOOSER_ACTION_OPEN,
                 confirm_func=None, browse_reason=None):
    """
    Helper function for launching a filechooser

    @param parent: Parent window for the filechooser
    @param dialog_name: String to use in the title bar of the filechooser.
    @param config: vmmConfig used by calling class
    @param conn: vmmConnection used by calling class
    @param start_folder: Folder the filechooser is viewing at startup
    @param _type: File extension to filter by (e.g. "iso", "png")
    @param dialog_type: Maps to FileChooserDialog 'action'
    @param confirm_func: Optional callback function if file is chosen.
    @param browse_reason: The vmmConfig.CONFIG_DIR* reason we are browsing.
        If set, this will override the 'folder' parameter with the gconf
        value, and store the user chosen path.

    """

    # Initial setup
    overwrite_confirm = False
    choose_button = gtk.STOCK_OPEN
    if dialog_type == gtk.FILE_CHOOSER_ACTION_SAVE:
        choose_button = gtk.STOCK_SAVE
        overwrite_confirm = True

    fcdialog = gtk.FileChooserDialog(dialog_name, parent,
                                     dialog_type,
                                     (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                      choose_button, gtk.RESPONSE_ACCEPT),
                                      None)
    fcdialog.set_default_response(gtk.RESPONSE_ACCEPT)

    # If confirm is set, warn about a file overwrite
    if confirm_func:
        overwrite_confirm = True
        fcdialog.connect("confirm-overwrite", confirm_func)
    fcdialog.set_do_overwrite_confirmation(overwrite_confirm)

    # Set file match pattern (ex. *.png)
    if _type != None:
        pattern = _type
        name = None
        if type(_type) is tuple:
            pattern = _type[0]
            name = _type[1]

        f = gtk.FileFilter()
        f.add_pattern("*." + pattern)
        if name:
            f.set_name(name)
        fcdialog.set_filter(f)

    # Set initial dialog folder
    if browse_reason:
        start_folder = config.get_default_directory(conn, browse_reason)

    if start_folder != None:
        if not os.access(start_folder, os.R_OK):
            fcdialog.set_current_folder(start_folder)

    # Run the dialog and parse the response
    response = fcdialog.run()
    fcdialog.hide()
    if (response == gtk.RESPONSE_ACCEPT):
        filename = fcdialog.get_filename()
        fcdialog.destroy()
        ret = filename
    else:
        fcdialog.destroy()
        ret = None

    # Store the chosen directory in gconf if necessary
    if ret and browse_reason and not ret.startswith("/dev"):
        config.set_default_directory(os.path.dirname(ret), browse_reason)

    return ret

def dup_lib_conn(config, libconn):
    return _dup_all_conn(config, None, libconn=libconn,
                         return_conn_class=False)

def dup_conn(config, conn, return_conn_class=False):
    return _dup_all_conn(config, conn, None,
                         return_conn_class=return_conn_class)

def _dup_all_conn(config, conn, libconn, return_conn_class):

    is_readonly = False

    if libconn:
        uri = libconn.getURI()
        is_test = uri.startswith("test")
        vmm = libconn
    else:
        is_test = conn.is_test_conn()
        is_readonly = conn.is_read_only()
        uri = conn.get_uri()
        vmm = conn.vmm

    if is_test:
        # Skip duplicating a test conn, since it doesn't maintain state
        # between instances
        return return_conn_class and conn or vmm

    if virtinst.support.support_threading():
        # Libvirt 0.6.0 implemented client side request threading: this
        # removes the need to actually duplicate the connection.
        return return_conn_class and conn or vmm

    logging.debug("Duplicating connection for async operation.")
    newconn = virtManager.connection.vmmConnection(config, uri, is_readonly)
    newconn.open()
    newconn.connectThreadEvent.wait()

    if return_conn_class:
        return newconn
    else:
        return newconn.vmm

def pretty_hv(gtype, domtype):
    """
    Convert XML <domain type='foo'> and <os><type>bar</type>
    into a more human relevant string.
    """

    gtype = gtype.lower()
    domtype = domtype.lower()

    label = domtype
    if domtype == "kvm":
        if gtype == "xen":
            label = "xenner"
    elif domtype == "xen":
        if gtype == "xen":
            label = "xen (paravirt)"
        elif gtype == "hvm":
            label = "xen (fullvirt)"
    elif domtype == "test":
        if gtype == "xen":
            label = "test (xen)"
        elif gtype == "hvm":
            label = "test (hvm)"

    return label

def connect_once(obj, signal, func, *args):
    id_list = []

    def wrap_func(*wrapargs):
        if id_list:
            obj.disconnect(id_list[0])

        return func(*wrapargs)

    conn_id = obj.connect(signal, wrap_func, *args)
    id_list.append(conn_id)

    return conn_id

def connect_opt_out(obj, signal, func, *args):
    id_list = []

    def wrap_func(*wrapargs):
        ret = func(*wrapargs)
        if ret and id_list:
            obj.disconnect(id_list[0])

    conn_id = obj.connect(signal, wrap_func, *args)
    id_list.append(conn_id)

    return conn_id

def idle_emit(self, signal, *args):
    """
    Safe wrapper for using 'self.emit' with gobject.idle_add
    """
    self.emit(signal, *args)
    return False

def _safe_wrapper(func, *args):
    gtk.gdk.threads_enter()
    try:
        return func(*args)
    finally:
        gtk.gdk.threads_leave()

def safe_idle_add(func, *args):
    """
    Make sure idle functions are run thread safe
    """
    return gobject.idle_add(_safe_wrapper, func, *args)

def safe_timeout_add(timeout, func, *args):
    """
    Make sure timeout functions are run thread safe
    """
    return gobject.timeout_add(timeout, _safe_wrapper, func, *args)

def uuidstr(rawuuid):
    hx = ['0','1','2','3','4','5','6','7','8','9','a','b','c','d','e','f']
    uuid = []
    for i in range(16):
        uuid.append(hx[((ord(rawuuid[i]) >> 4) & 0xf)])
        uuid.append(hx[(ord(rawuuid[i]) & 0xf)])
        if i == 3 or i == 5 or i == 7 or i == 9:
            uuid.append('-')
    return "".join(uuid)

def bind_escape_key_close(vmmobj):
    def close_on_escape(src, event):
        if gtk.gdk.keyval_name(event.keyval) == "Escape":
            vmmobj.close()

    vmmobj.topwin.connect("key-press-event", close_on_escape)

def safe_set_prop(self, prop, value):
    """
    Make sure a gtk property is supported, and set to value

    Return True if property was sucessfully set, False otherwise
    """

    try:
        self.get_property(prop)
        self.set_property(prop, value)
        return True
    except TypeError:
        return False

def iface_in_use_by(conn, name):
    use_str = ""
    for i in conn.list_interface_names():
        iface = conn.get_interface(i)
        if name in iface.get_slave_names():
            if use_str:
                use_str += ", "
            use_str += iface.get_name()

    return use_str

