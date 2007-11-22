/* -- THIS FILE IS GENERATED - DO NOT EDIT *//* -*- Mode: C; c-basic-offset: 4 -*- */

#include <Python.h>



#line 3 "./pysparklinemodule.override"
#include <Python.h>               
#include "pygobject.h"
#include "sparkline.h"
#include "cellrenderersparkline.h"
#line 13 "pysparklinemodule.c"


/* ---------- types from other modules ---------- */
static PyTypeObject *_PyGtkCellRenderer_Type;
#define PyGtkCellRenderer_Type (*_PyGtkCellRenderer_Type)
static PyTypeObject *_PyGtkDrawingArea_Type;
#define PyGtkDrawingArea_Type (*_PyGtkDrawingArea_Type)


/* ---------- forward type declarations ---------- */
PyTypeObject G_GNUC_INTERNAL PyGtkCellRendererSparkline_Type;
PyTypeObject G_GNUC_INTERNAL PyGtkSparkline_Type;

#line 27 "pysparklinemodule.c"



/* ----------- GtkCellRendererSparkline ----------- */

static int
_wrap_gtk_cell_renderer_sparkline_new(PyGObject *self, PyObject *args, PyObject *kwargs)
{
    static char* kwlist[] = { NULL };

    if (!PyArg_ParseTupleAndKeywords(args, kwargs,
                                     ":sparkline.CellRendererSparkline.__init__",
                                     kwlist))
        return -1;

    pygobject_constructv(self, 0, NULL);
    if (!self->obj) {
        PyErr_SetString(
            PyExc_RuntimeError, 
            "could not create sparkline.CellRendererSparkline object");
        return -1;
    }
    return 0;
}

PyTypeObject G_GNUC_INTERNAL PyGtkCellRendererSparkline_Type = {
    PyObject_HEAD_INIT(NULL)
    0,                                 /* ob_size */
    "sparkline.CellRendererSparkline",                   /* tp_name */
    sizeof(PyGObject),          /* tp_basicsize */
    0,                                 /* tp_itemsize */
    /* methods */
    (destructor)0,        /* tp_dealloc */
    (printfunc)0,                      /* tp_print */
    (getattrfunc)0,       /* tp_getattr */
    (setattrfunc)0,       /* tp_setattr */
    (cmpfunc)0,           /* tp_compare */
    (reprfunc)0,             /* tp_repr */
    (PyNumberMethods*)0,     /* tp_as_number */
    (PySequenceMethods*)0, /* tp_as_sequence */
    (PyMappingMethods*)0,   /* tp_as_mapping */
    (hashfunc)0,             /* tp_hash */
    (ternaryfunc)0,          /* tp_call */
    (reprfunc)0,              /* tp_str */
    (getattrofunc)0,     /* tp_getattro */
    (setattrofunc)0,     /* tp_setattro */
    (PyBufferProcs*)0,  /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,                      /* tp_flags */
    NULL,                        /* Documentation string */
    (traverseproc)0,     /* tp_traverse */
    (inquiry)0,             /* tp_clear */
    (richcmpfunc)0,   /* tp_richcompare */
    offsetof(PyGObject, weakreflist),             /* tp_weaklistoffset */
    (getiterfunc)0,          /* tp_iter */
    (iternextfunc)0,     /* tp_iternext */
    (struct PyMethodDef*)NULL, /* tp_methods */
    (struct PyMemberDef*)0,              /* tp_members */
    (struct PyGetSetDef*)0,  /* tp_getset */
    NULL,                              /* tp_base */
    NULL,                              /* tp_dict */
    (descrgetfunc)0,    /* tp_descr_get */
    (descrsetfunc)0,    /* tp_descr_set */
    offsetof(PyGObject, inst_dict),                 /* tp_dictoffset */
    (initproc)_wrap_gtk_cell_renderer_sparkline_new,             /* tp_init */
    (allocfunc)0,           /* tp_alloc */
    (newfunc)0,               /* tp_new */
    (freefunc)0,             /* tp_free */
    (inquiry)0              /* tp_is_gc */
};



/* ----------- GtkSparkline ----------- */

static int
_wrap_gtk_sparkline_new(PyGObject *self, PyObject *args, PyObject *kwargs)
{
    static char* kwlist[] = { NULL };

    if (!PyArg_ParseTupleAndKeywords(args, kwargs,
                                     ":sparkline.Sparkline.__init__",
                                     kwlist))
        return -1;

    pygobject_constructv(self, 0, NULL);
    if (!self->obj) {
        PyErr_SetString(
            PyExc_RuntimeError, 
            "could not create sparkline.Sparkline object");
        return -1;
    }
    return 0;
}

PyTypeObject G_GNUC_INTERNAL PyGtkSparkline_Type = {
    PyObject_HEAD_INIT(NULL)
    0,                                 /* ob_size */
    "sparkline.Sparkline",                   /* tp_name */
    sizeof(PyGObject),          /* tp_basicsize */
    0,                                 /* tp_itemsize */
    /* methods */
    (destructor)0,        /* tp_dealloc */
    (printfunc)0,                      /* tp_print */
    (getattrfunc)0,       /* tp_getattr */
    (setattrfunc)0,       /* tp_setattr */
    (cmpfunc)0,           /* tp_compare */
    (reprfunc)0,             /* tp_repr */
    (PyNumberMethods*)0,     /* tp_as_number */
    (PySequenceMethods*)0, /* tp_as_sequence */
    (PyMappingMethods*)0,   /* tp_as_mapping */
    (hashfunc)0,             /* tp_hash */
    (ternaryfunc)0,          /* tp_call */
    (reprfunc)0,              /* tp_str */
    (getattrofunc)0,     /* tp_getattro */
    (setattrofunc)0,     /* tp_setattro */
    (PyBufferProcs*)0,  /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,                      /* tp_flags */
    NULL,                        /* Documentation string */
    (traverseproc)0,     /* tp_traverse */
    (inquiry)0,             /* tp_clear */
    (richcmpfunc)0,   /* tp_richcompare */
    offsetof(PyGObject, weakreflist),             /* tp_weaklistoffset */
    (getiterfunc)0,          /* tp_iter */
    (iternextfunc)0,     /* tp_iternext */
    (struct PyMethodDef*)NULL, /* tp_methods */
    (struct PyMemberDef*)0,              /* tp_members */
    (struct PyGetSetDef*)0,  /* tp_getset */
    NULL,                              /* tp_base */
    NULL,                              /* tp_dict */
    (descrgetfunc)0,    /* tp_descr_get */
    (descrsetfunc)0,    /* tp_descr_set */
    offsetof(PyGObject, inst_dict),                 /* tp_dictoffset */
    (initproc)_wrap_gtk_sparkline_new,             /* tp_init */
    (allocfunc)0,           /* tp_alloc */
    (newfunc)0,               /* tp_new */
    (freefunc)0,             /* tp_free */
    (inquiry)0              /* tp_is_gc */
};



/* ----------- functions ----------- */

const PyMethodDef sparkline_functions[] = {
    { NULL, NULL, 0, NULL }
};

/* initialise stuff extension classes */
void
sparkline_register_classes(PyObject *d)
{
    PyObject *module;

    if ((module = PyImport_ImportModule("gtk")) != NULL) {
        _PyGtkCellRenderer_Type = (PyTypeObject *)PyObject_GetAttrString(module, "CellRenderer");
        if (_PyGtkCellRenderer_Type == NULL) {
            PyErr_SetString(PyExc_ImportError,
                "cannot import name CellRenderer from gtk");
            return ;
        }
        _PyGtkDrawingArea_Type = (PyTypeObject *)PyObject_GetAttrString(module, "DrawingArea");
        if (_PyGtkDrawingArea_Type == NULL) {
            PyErr_SetString(PyExc_ImportError,
                "cannot import name DrawingArea from gtk");
            return ;
        }
    } else {
        PyErr_SetString(PyExc_ImportError,
            "could not import gtk");
        return ;
    }


#line 201 "pysparklinemodule.c"
    pygobject_register_class(d, "GtkCellRendererSparkline", GTK_TYPE_CELL_RENDERER_SPARKLINE, &PyGtkCellRendererSparkline_Type, Py_BuildValue("(O)", &PyGtkCellRenderer_Type));
    pyg_set_object_has_new_constructor(GTK_TYPE_CELL_RENDERER_SPARKLINE);
    pygobject_register_class(d, "GtkSparkline", GTK_TYPE_SPARKLINE, &PyGtkSparkline_Type, Py_BuildValue("(O)", &PyGtkDrawingArea_Type));
    pyg_set_object_has_new_constructor(GTK_TYPE_SPARKLINE);
}
