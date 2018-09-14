"""
.. module:: Confusion Matrix
   :synopsis:  Confusion Matrix

.. moduleauthor:: Ambra Demontis <ambra.demontis@diee.unica.it>

"""
from sklearn.metrics import confusion_matrix
from prlib.array import CArray
from prlib.peval.metrics import CMetric


class CMetricConfusionMatrix(CMetric):

    def _performance_score(self, y_true, y_pred):
        """Computes the Confusion Matrix.

        Parameters
        ----------
        y_true : CArray
            Ground truth (true) labels or target scores.
        y_pred : CArray
            Predicted labels, as returned by a CClassifier.

        Returns
        -------
        CArray
            Confusion matrix with shape = [n_classes, n_classes].

        """
        y_true = CArray(y_true)
        y_pred = CArray(y_pred)
        return CArray(confusion_matrix(y_true.tondarray(),
                                       y_pred.tondarray()))
