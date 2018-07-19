"""Implementations for the debug VM."""

from copy import copy
from typing import Callable
import numpy as np

from .. import dtype as types
from ..utils import Registry

from . import ops as primops


py_implementations: Registry[primops.Primitive, Callable] = Registry()
vm_implementations: Registry[primops.Primitive, Callable] = Registry()
py_register = py_implementations.register
vm_register = vm_implementations.register


def register(prim):
    """Register an implementation for this primitive.

    The same implementation will be used for both the VM and for the pure
    Python version.
    """
    def deco(fn):
        vm_register(prim)(lambda vm, *args: fn(*args))
        return py_register(prim)(fn)
    return deco


def _assert_scalar(*args):
    # TODO: These checks should be stricter, e.g. require that all args
    # have exactly the same type, but right now there is some mixing between
    # numpy types and int/float.
    for x in args:
        if isinstance(x, np.ndarray):
            if x.shape != ():
                msg = f'Expected scalar, not array with shape {x.shape}'
                raise TypeError(msg)
        elif not isinstance(x, (int, float)):
            raise TypeError(f'Expected scalar, not {type(x)}')


@register(primops.scalar_add)
def scalar_add(x, y):
    """Implement `scalar_add`."""
    _assert_scalar(x, y)
    return x + y


@register(primops.scalar_sub)
def scalar_sub(x, y):
    """Implement `scalar_sub`."""
    _assert_scalar(x, y)
    return x - y


@register(primops.scalar_mul)
def scalar_mul(x, y):
    """Implement `scalar_mul`."""
    _assert_scalar(x, y)
    return x * y


@register(primops.scalar_div)
def scalar_div(x, y):
    """Implement `scalar_div`."""
    _assert_scalar(x, y)
    return x / y


@register(primops.scalar_mod)
def scalar_mod(x, y):
    """Implement `scalar_mod`."""
    _assert_scalar(x, y)
    return x % y


@register(primops.scalar_pow)
def scalar_pow(x, y):
    """Implement `scalar_pow`."""
    _assert_scalar(x, y)
    return x ** y


@register(primops.scalar_uadd)
def scalar_uadd(x):
    """Implement `scalar_uadd`."""
    _assert_scalar(x)
    return x


@register(primops.scalar_usub)
def scalar_usub(x):
    """Implement `scalar_usub`."""
    _assert_scalar(x)
    return -x


@register(primops.scalar_eq)
def scalar_eq(x, y):
    """Implement `scalar_eq`."""
    _assert_scalar(x, y)
    return x == y


@register(primops.scalar_lt)
def scalar_lt(x, y):
    """Implement `scalar_lt`."""
    _assert_scalar(x, y)
    return x < y


@register(primops.scalar_gt)
def scalar_gt(x, y):
    """Implement `scalar_gt`."""
    _assert_scalar(x, y)
    return x > y


@register(primops.scalar_ne)
def scalar_ne(x, y):
    """Implement `scalar_ne`."""
    _assert_scalar(x, y)
    return x != y


@register(primops.scalar_le)
def scalar_le(x, y):
    """Implement `scalar_le`."""
    _assert_scalar(x, y)
    return x <= y


@register(primops.scalar_ge)
def scalar_ge(x, y):
    """Implement `scalar_ge`."""
    _assert_scalar(x, y)
    return x >= y


@register(primops.bool_not)
def bool_not(x):
    """Implement `bool_not`."""
    assert x is True or x is False
    return not x


@register(primops.typeof)
def typeof(x):
    """Implement typeof."""
    if isinstance(x, types.Type) or isinstance(x, type):
        return types.Type
    elif isinstance(x, bool):
        return types.Bool()
    elif isinstance(x, int):
        return types.Int(64)
    elif isinstance(x, float):
        return types.Float(64)
    elif isinstance(x, tuple):
        return types.Tuple(map(typeof, x))
    elif isinstance(x, list) and len(x) > 0:
        type0, *rest = map(typeof, x)
        if any(t != type0 for t in rest):
            raise TypeError(f'All list elements should have same type')
        return types.List(type0)
    else:
        return types.External(type(x))


def hastype_helper(t, model):
    """Check that type t is represented by model."""
    if t == model:
        return True
    elif isinstance(model, type) and issubclass(model, types.Type):
        return isinstance(t, model)
    else:
        return False


@register(primops.hastype)
def hastype(x, t):
    """Implement `hastype`."""
    return hastype_helper(typeof(x), t)


@register(primops.cons_tuple)
def cons_tuple(head, tail):
    """Implement `cons_tuple`."""
    return (head,) + tail


@register(primops.head)
def head(tup):
    """Implement `head`."""
    return tup[0]


@register(primops.tail)
def tail(tup):
    """Implement `tail`."""
    return tup[1:]


@py_register(primops.getitem)
def getitem(data, item):
    """Implement `getitem`."""
    return data[item]


@vm_register(primops.getitem)
def _vm_getitem(vm, data, item):
    """Implement `getitem`."""
    return vm.convert(data[item])


@register(primops.setitem)
def setitem(data, item, value):
    """Implement `setitem`."""
    if isinstance(data, tuple):
        return tuple(value if i == item else x
                     for i, x in enumerate(data))
    else:
        data2 = copy(data)
        data2[item] = value
        return data2


@vm_register(primops.getattr)
def _vm_getattr(vm, data, attr):
    """Implement `getattr`."""
    return vm.convert(getattr(data, attr))


py_setattr = setattr


@register(primops.setattr)
def setattr(data, attr, value):
    """Implement `setattr`."""
    data2 = copy(data)
    py_setattr(data2, attr, value)
    return data2


@register(primops.shape)
def shape(array):
    """Implement `shape`."""
    return array.shape


@py_register(primops.array_map)
def array_map(fn, array):
    """Implement `array_map`."""
    def f(ary):
        it = np.nditer([ary, None])
        for x, y in it:
            y[...] = fn(x)
        return it.operands[1]
    return np.apply_along_axis(f, 0, array)


@vm_register(primops.array_map)
def _array_map_vm(vm, fn, array):
    def fn_(x):
        return vm.call(fn, (x,))
    return array_map(fn_, array)


@py_register(primops.array_scan)
def array_scan(fn, init, array, axis):
    """Implement `array_scan`."""
    # This is inclusive scan because it's easier to implement
    # We will have to discuss what semantics we want later
    def f(ary):
        val = init
        it = np.nditer([ary, None])
        for x, y in it:
            val = fn(val, x)
            y[...] = val
        return it.operands[1]
    return np.apply_along_axis(f, axis, array)


@vm_register(primops.array_scan)
def _array_scan_vm(vm, fn, init, array, axis):
    def fn_(a, b):
        return vm.call(fn, [a, b])
    return array_scan(fn_, init, array, axis)


@py_register(primops.array_reduce)
def array_reduce(fn, init, array, axis):
    """Implement `array_reduce`."""
    def f(ary):
        val = init
        it = np.nditer([ary])
        for x in it:
            val = fn(val, x)
        return val
    return np.apply_along_axis(f, axis, array)


@vm_register(primops.array_reduce)
def _array_reduce_vm(vm, fn, init, array, axis):
    def fn_(a, b):
        return vm.call(fn, [a, b])
    return array_reduce(fn_, init, array, axis)


@register(primops.distribute)
def distribute(v, shape):
    """Implement `distribute`."""
    return np.broadcast_to(v, shape)


@register(primops.reshape)
def reshape(v, shape):
    """Implement `reshape`."""
    return np.reshape(v, shape)


@register(primops.dot)
def dot(a, b):
    """Implement `dot`."""
    return np.dot(a, b)


@register(primops.return_)
def return_(x):
    """Implement `return_`."""
    return x


@py_register(primops.list_map)
def list_map(f, xs):
    """Implement `list_map` in pure Python."""
    return list(map(f, xs))


@vm_register(primops.list_map)
def _list_map_vm(vm, f, xs):
    """Implement `list_map` for Myia's VM."""
    def f_(*args):
        return vm.call(f, args)
    return list(map(f_, xs))


@vm_register(primops.resolve)
def _resolve_vm(vm, data, item):
    """Implement `resolve` for the VM."""
    # There is no Python implementation for this one.
    value = data[item]
    return vm.convert(value)


@py_register(primops.partial)
def partial(f, *args):
    """Implement `partial`."""
    def res(*others):
        return f(*(args + others))
    return res


@register(primops.iter)
def _iter(xs):
    """Implement `iter`."""
    return (0, xs)


@register(primops.hasnext)
def _hasnext(it):
    """Implement `hasnext`."""
    n, data = it
    return n < len(data)


@register(primops.next)
def _next(it):
    """Implement `next`."""
    n, data = it
    return (data[n], (n + 1, data))
