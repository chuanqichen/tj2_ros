import time
import numpy as np
from tj2_tools.robot_state import DeltaTimer
from tj2_tools.robot_state import Simple3DState

from .delta_measurement import DeltaMeasurement


class InputVector:
    def __init__(self, stale_filter_time, smooth_k=None):
        self.odom_timer = DeltaTimer()
        self.stale_meas_timer = time.time()
        self.stale_filter_time = stale_filter_time
        self.meas = DeltaMeasurement(smooth_k)
        self.meas_input = np.array([0.0, 0.0, 0.0, 0.0])
        self.vector = np.array([0.0, 0.0, 0.0, 0.0])
        self.odom_state = Simple3DState()
        self.meas_state = Simple3DState()
    
    def set_smooth_k(self, smooth_k):
        self.meas.set_smooth_k(smooth_k)

    def odom_update(self, odom_state: Simple3DState):
        dt = self.odom_timer.dt(odom_state.stamp)
        self.vector = np.array([odom_state.vx, odom_state.vy, odom_state.vz, odom_state.vt])
        self.odom_state = odom_state
        self.vector -= self.meas_input
        if time.time() - self.stale_meas_timer > self.stale_filter_time:
            self.meas_input = np.array([0.0, 0.0, 0.0, 0.0])
        return dt

    def meas_update(self, meas_state: Simple3DState):
        new_state = self.meas.update(meas_state)
        self.meas_state = new_state
        self.meas_input = np.array([new_state.vx, new_state.vy, new_state.vz, new_state.vt])
        self.stale_meas_timer = time.time()
        return new_state

    def get_vector(self):
        return self.vector
