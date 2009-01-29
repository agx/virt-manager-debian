/*
 * Copyright (C) 2006 Red Hat, Inc.
 * Copyright (C) 2006 Daniel P. Berrange <berrange@redhat.com>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
 */

#include <pygobject.h>

void sparkline_register_classes (PyObject *d);
extern PyMethodDef sparkline_functions[];

DL_EXPORT(void)
initsparkline(void)
{
    PyObject *m, *d;

    init_pygobject ();

    m = Py_InitModule ("sparkline", sparkline_functions);
    d = PyModule_GetDict (m);

    sparkline_register_classes(d);

    if (PyErr_Occurred ()) {
        Py_FatalError ("can't initialise module sparkline");
    }
}