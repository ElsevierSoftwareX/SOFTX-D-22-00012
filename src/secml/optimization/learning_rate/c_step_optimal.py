
from secml.optimization.learning_rate import CStep


class CStepOptimal(CStep):
    """Optimal step.

    For every iteration, the step is compute as
            1/(alfa*t)
    t: t-th iteration

    Attributes
    ----------
    class_type : 'optimal'

    """
    __class_type = 'optimal'

    def __init__(self, initial_step_value=0, alfa=1):
        '''
        Sets the initial value of step
        '''
        super(CStepOptimal, self).__init__(
            initial_step_value=initial_step_value)
        self.alfa = alfa

    def get_actual_step(self, iter):
        if iter is 0:
            return 1
        else:
            return float(1) / (self.alfa * iter)
