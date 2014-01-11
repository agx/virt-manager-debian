#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free  Software Foundation; either version 2 of the License, or
# (at your option)  any later version.
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

import logging
import os

import virtinst
from tests import utils

# pylint: disable=W0212
# Access to protected member, needed to unittest stuff

# Force certain helpers to return consistent values
virtinst.util.is_blktap_capable = lambda: False
virtinst.util.default_bridge = lambda ignore1: ["bridge", "eth0"]
virtinst.Guest._open_uri = lambda ignore1, ignore2: None

# Setup logging
rootLogger = logging.getLogger()
for handler in rootLogger.handlers:
    rootLogger.removeHandler(handler)

logging.basicConfig(level=logging.DEBUG,
                    format="%(levelname)-8s %(message)s")

if utils.get_debug():
    rootLogger.setLevel(logging.DEBUG)
else:
    rootLogger.setLevel(logging.ERROR)
