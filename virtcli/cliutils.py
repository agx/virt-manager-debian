#
# Copyright (C) 2011, 2013 Red Hat, Inc.
# Copyright (C) 2011 Cole Robinson <crobinso@redhat.com>
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

import gettext
import locale

from virtcli import cliconfig


def setup_i18n():
    try:
        locale.setlocale(locale.LC_ALL, '')
    except:
        # Can happen if user passed a bogus LANG
        pass

    gettext.install("virt-manager", cliconfig.gettext_dir)
    gettext.bindtextdomain("virt-manager", cliconfig.gettext_dir)
