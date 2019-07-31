from secml.ml.classifiers.tests import CClassifierTestCases

from secml.data.loader import CDLIris, CDLRandomBlobs
from secml.ml.classifiers import CClassifierDecisionTree


class TestCClassifierDecisionTree(CClassifierTestCases):
    """Unit test for CDecisionTree."""

    def setUp(self):
        self.dataset = CDLIris().load()
        self.dec_tree = CClassifierDecisionTree()

    def test_classify(self):
        """Test for predict method. """
        self.logger.info("Testing decision tree classifier training ")
        self.dec_tree.fit(self.dataset)

        self.logger.info("Testing classification with trees")

        self.logger.info(
            "Number of classes: {:}".format(self.dec_tree.n_classes))

        y, result = self.dec_tree.predict(
            self.dataset.X[0, :], return_decision_function=True)
        self.logger.info(
            "Probability of affinity to each class: {:}".format(result))
        self.logger.info("Class of affinity: {:}".format(y))
        self.assertEqual(self.dataset.Y[0], y, "Wrong classification")

        y, result = self.dec_tree.predict(
            self.dataset.X[50, :], return_decision_function=True)
        self.logger.info(
            "Probability of affinity to each class: {:}".format(result))
        self.logger.info("Class of affinity: {:}".format(y))
        self.assertEqual(self.dataset.Y[50], y, "Wrong classification")

        y, result = self.dec_tree.predict(
            self.dataset.X[120, :], return_decision_function=True)
        self.logger.info(
            "Probability of affinity to each class: {:}".format(result))
        self.logger.info("Class of affinity: {:}".format(y))
        self.assertEqual(self.dataset.Y[120], y, "Wrong classification")

    def test_fun(self):
        """Test for decision_function() and predict() methods."""
        self._test_fun(self.dec_tree, self.dataset.todense())
        self._test_fun(self.dec_tree, self.dataset.tosparse())

    def test_preprocess(self):
        """Test classifier with preprocessors inside."""
        # All linear transformations
        self._test_preprocess(self.dataset, self.dec_tree,
                              ['min-max', 'mean-std'],
                              [{'feature_range': (-1, 1)}, {}])

        # Mixed linear/nonlinear transformations
        self._test_preprocess(self.dataset, self.dec_tree,
                              ['pca', 'unit-norm'], [{}, {}])

    def test_plot(self):
        ds = CDLRandomBlobs(n_samples=100, centers=3, n_features=2,
                            random_state=1).load()
        fig = self._test_plot(self.dec_tree, ds)
        fig.savefig('test_c_classifier_decision_tree.pdf')


if __name__ == '__main__':
    CClassifierTestCases.main()
