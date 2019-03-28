"""
.. module:: COptimizer
   :synopsis: Interface for function optimization and minimization.

.. moduleauthor:: Marco Melis <marco.melis@diee.unica.it>
.. moduleauthor:: Battista Biggio <battista.biggio@diee.unica.it>

"""
from abc import ABCMeta, abstractmethod
import six

from secml.core import CCreator
from secml.optim.function import CFunction
from secml.optim.constraints import CConstraint


@six.add_metaclass(ABCMeta)
class COptimizer(CCreator):
    """
    Class serving as interface to define optimization problems in the form:

    minimize f(x)
    s.t. gi(x) <= 0, i=1,...,m  (inequality constraints)
         hj(x) = 0, j = 1,..., n (equality constraints)

    Parameters
    ----------
    fun : CFunction
        The objective function to be optimized,
        along with 1st-order (Jacobian) and 2nd-order (Hessian) derivatives
        (if available).

    """
    __super__ = 'COptimizer'

    def __init__(self, fun, constr=None, bounds=None, discrete=False):

        # this is the function passed by the user to be maximized or minimized
        # FIXME: clear is deprecated. Remove these attributes set to none
        #  after removing the use of clear
        self._f = None
        self._constr = None
        self._bounds = None
        self._discrete = None

        # this is the internal function to be always minimized
        self._fun = None  # by default, minimize f(x), so fun=f
        self._f_seq = None

        # calling setters to check types
        self.f = fun  # this will set both f and fun
        self.constr = constr
        self.bounds = bounds
        self.discrete = discrete

        COptimizer.__clear(self)

    ##########################################
    #            INTERNALS
    ##########################################
    def __clear(self):
        """Reset the object."""
        if self.constr is not None:
            self.constr.clear()
        if self.bounds is not None:
            self.bounds.clear()

        self._x_opt = None  # solution point
        self._f_opt = None  # last score f_seq[-1]
        self._f_seq = None  # sequence of fun values at each iteration
        self._x_seq = None  # sequence of x values at each iteration
        self._f_eval = 0
        self._grad_eval = 0

    def __is_clear(self):
        """Returns True if object is clear."""
        if self.constr is not None and not self.constr.is_clear():
            return False
        if self.bounds is not None and not self.bounds.is_clear():
            return False

        if self._x_opt is not None or self._f_opt is not None:
            return False
        if self._f_seq is not None or self._x_seq is not None:
            return False

        if self._f_eval + self._grad_eval != 0:
            return False

        return True

    ###########################################################################
    #                           READ-ONLY ATTRIBUTES
    ###########################################################################
    @property
    def n_dim(self):
        return int(self._fun.n_dim)

    @property
    def x_opt(self):
        return self._x_opt

    @property
    def f_opt(self):
        return self._f_seq[-1].item()

    @property
    def x_seq(self):
        return self._x_seq

    @property
    def f_seq(self):
        return self._f_seq

    @property
    def f_eval(self):
        return self._f_eval

    @property
    def grad_eval(self):
        return self._grad_eval

    ###########################################################################
    #                           READ-WRITE ATTRIBUTES
    ###########################################################################

    @property
    def f(self):
        """Returns objective function"""
        return self._f

    @f.setter
    def f(self, f):
        if not isinstance(f, CFunction):
            raise TypeError(
                "Input parameter is not a `CFunction` object.")
        self._f = f
        self._fun = f

        # changing optimization problem requires clearing the solver
        self.__clear()

    @property
    def constr(self):
        return self._constr

    @constr.setter
    def constr(self, constr):

        # constr is optional
        if constr is None:
            self._constr = None
            self.__clear()
            return

        if not isinstance(constr, CConstraint):
            raise TypeError(
                "Input parameter is not a `CConstraint` object.")

        if constr.class_type != 'l1' and constr.class_type != 'l2':
            raise TypeError(
                "Only l1 or l2 `CConstraint` objects are accepted as input.")

        self._constr = constr
        # changing optimization problem requires clearing the solver
        self.__clear()

    @property
    def bounds(self):
        return self._bounds

    @bounds.setter
    def bounds(self, bounds):

        # bounds is optional
        if bounds is None:
            self._bounds = None
            self.__clear()
            return

        if not isinstance(bounds, CConstraint):
            raise TypeError(
                "Input parameter is not a `CConstraint` object.")

        if bounds.class_type != 'box':
            raise TypeError(
                "Only box `CConstraint` objects are accepted as input.")

        self._bounds = bounds
        # changing optimization problem requires clearing the solver
        self.__clear()

    @property
    def discrete(self):
        """Returns True if feature space is discrete, False if continuous."""
        return self._discrete

    @discrete.setter
    def discrete(self, value):
        """Set to True if feature space is discrete, False if continuous."""
        self._discrete = bool(value)
        # changing optimization problem requires clearing the solver
        self.__clear()

    ##########################################
    #            PUBLIC METHODS
    ##########################################

    @abstractmethod
    def minimize(self, x_init, *args, **kwargs):
        raise NotImplementedError('Function `minimize` is not implemented.')

    def maximize(self, x_init, *args, **kwargs):

        # invert sign of fun(x) and grad(x) and run minimize
        self._fun = CFunction(
            fun=lambda z: -self._f.fun(z, *args),
            gradient=lambda z: -self._f.gradient(z, *args))

        x = self.minimize(x_init, *args, **kwargs)

        # fix solution variables
        self._f_seq = -self._f_seq

        # restore fun to its default
        self._fun = self.f

        return x
