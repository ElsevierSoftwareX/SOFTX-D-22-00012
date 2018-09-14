"""
.. module:: MetricTestError
   :synopsis: Performance Metric: Test Error

.. moduleauthor:: Marco Melis <marco.melis@diee.unica.it>

"""
import sklearn.metrics as skm

from prlib.array import CArray
from prlib.peval.metrics import CMetric


class CMetricTestError(CMetric):
    """Performance evaluation metric: Test Error.

    Test Error score is the percentage (inside 0/1 range)
    of wrongly predicted labels (inverse of accuracy).

    The metric uses:
     - y_true (true ground labels)
     - y_pred (predicted labels)

    Examples
    --------
    >>> from prlib.peval.metrics import CMetricTestError
    >>> from prlib.array import CArray

    >>> peval = CMetricTestError()
    >>> print peval.performance_score(CArray([0, 1, 2, 3]), CArray([0, 1, 1, 3]))
    0.25

    """
    class_type = 'test_error'
    best_value = 0.0

    def _performance_score(self, y_true, y_pred):
        """Computes the Accuracy score.

        Parameters
        ----------
        y_true : CArray
            Ground truth (true) labels or target scores.
        y_pred : CArray
            Predicted labels, as returned by a CClassifier.

        Returns
        -------
        metric : float
            Returns metric value as float.

        """
        return 1.0 - float(skm.accuracy_score(y_true.tondarray(),
                                              y_pred.tondarray()))
