import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from scipy.spatial.transform import Rotation

from tj2_tools.particle_filter.state import FilterState


class ParticleFilterPlotterBase:
    def __init__(self, tf_to_odom=True, plot_delay=0.01):
        self.plot_delay = plot_delay
        self.tf_to_odom = tf_to_odom
        self.fig = None
        self.ax = None
        self.odom_state = FilterState()
        self.meas_states = {}
        self.is_paused = False

        self.ax_vel = None

        self.timestamps = []
        self.x_vel_data = []
        self.y_vel_data = []
        self.z_vel_data = []

        self.init()

    def init(self):
        self.fig = plt.figure()
        self.fig.canvas.mpl_connect('key_press_event', self.on_press)

        plt.tight_layout()
        plt.ion()
        self.fig.show()

    def update_odom(self, state):
        self.odom_state = state

    def update_measure(self, name, state):
        self.meas_states[name] = state

    def draw(self, timestamp, pf, label):
        raise NotImplemented

    def clear(self):
        plt.cla()

    def on_press(self, event):
        if event.key == ' ':
            self.is_paused = not self.is_paused

    def pause(self):
        self.fig.canvas.start_event_loop(self.plot_delay)
        self.fig.canvas.flush_events()
        # plt.pause(self.plot_delay)

    def base_link_to_odom(self, state, x, y, z):
        point = np.array([x, y, z])
        if self.tf_to_odom:
            angle = state.theta
            # tf_mat = np.array([
            #     [np.cos(angle), -np.sin(angle), state.x],
            #     [np.sin(angle), np.cos(angle), state.y],
            #     [0.0, 0.0,  1.0]
            # ])
            # point = np.array([x, y, 1.0])
            # tf_point = np.dot(tf_mat, point)
            rot_mat = Rotation.from_euler("z", angle)

            tf_point = np.dot(rot_mat.as_matrix(), point)
            tf_point[0] += state.x
            tf_point[1] += state.y
            tf_point[2] += state.z
            return tf_point
        else:
            return point

    def velocity_base_link_to_odom(self, state, vx, vy, vz):
        velocity = np.array([-vx, -vy, -vz])
        if self.tf_to_odom:
            angle = state.theta
            rot_mat = Rotation.from_euler("z", angle)

            tf_vel = np.dot(rot_mat.as_matrix(), velocity)
            tf_vel[0] += state.vx
            tf_vel[1] += state.vy
            tf_vel[2] += state.vz
            return tf_vel
        else:
            return velocity

    def stop(self):
        plt.ioff()
        plt.show()


class ParticleFilterPlotter3D(ParticleFilterPlotterBase):
    def __init__(self, x_window, y_window, z_window, tf_to_odom=True, plot_delay=0.01):
        super(ParticleFilterPlotter3D, self).__init__(tf_to_odom, plot_delay)
        self.x_window = x_window
        self.y_window = y_window
        self.z_window = z_window

    def init(self):
        super(ParticleFilterPlotter3D, self).init()
        self.ax = self.fig.add_subplot(111, projection='3d')

    def draw(self, timestamp, pf, label):
        try:
            mu, var = pf.estimate()
        except ZeroDivisionError:
            return

        particles = self.base_link_to_odom(self.odom_state, pf.particles[:, 0], pf.particles[:, 1],
                                           pf.particles[:, 2])
        self.ax.scatter(particles[0], particles[1], particles[2], marker='.', s=1, color='k', alpha=0.5)
        self.ax.set_xlim(-self.x_window / 2, self.x_window / 2)
        self.ax.set_ylim(-self.y_window / 2, self.y_window / 2)
        self.ax.set_zlim(0.0, self.z_window)

        odom_mu = self.base_link_to_odom(self.odom_state, mu[0], mu[1], mu[2])
        self.ax.scatter(odom_mu[0], odom_mu[1], odom_mu[2], color='g', s=25)

        self.ax.scatter(self.odom_state.x, self.odom_state.y, self.odom_state.z, marker='*', color='b', s=25)

        for name, meas_state in self.meas_states.items():
            if self.odom_state.stamp - meas_state.stamp < 0.25:
                odom_meas = self.base_link_to_odom(self.odom_state, meas_state.x, meas_state.y, meas_state.z)
                self.ax.scatter(odom_meas[0], odom_meas[1], odom_meas[2], marker='*', color='r', s=25)

        # self.ax.text(odom_mu[0], odom_mu[1], odom_mu[2], label, transform=self.ax.transAxes, fontsize=14,
        #              verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        self.ax.text(odom_mu[0], odom_mu[1], odom_mu[2], label, color="black")


class ParticleFilterPlotter2D(ParticleFilterPlotterBase):
    def __init__(self, x_window, y_window, tf_to_odom=True, plot_delay=0.01):
        super(ParticleFilterPlotter2D, self).__init__(tf_to_odom, plot_delay)
        self.x_window = x_window
        self.y_window = y_window

    def init(self):
        super(ParticleFilterPlotter2D, self).init()
        self.ax = self.fig.add_subplot(2, 1, 1)
        self.ax_vel = self.fig.add_subplot(2, 1, 2)

    def draw(self, timestamp, pf, label):
        try:
            mu, var = pf.estimate()
        except ZeroDivisionError:
            return

        x, y, z, vx, vy, vz = mu

        self.ax.clear()
        particles = self.base_link_to_odom(
            self.odom_state,
            pf.particles[:, 0], pf.particles[:, 1], pf.particles[:, 2]
        )

        tfd_velocities = self.velocity_base_link_to_odom(
            self.odom_state,
            vx, vy, vz
        )

        self.ax.scatter(particles[0], particles[1], marker='.', s=1, color='k', alpha=0.5)
        self.ax.set_xlim(-self.x_window / 2, self.x_window / 2)
        self.ax.set_ylim(-self.y_window / 2, self.y_window / 2)

        odom_mu = self.base_link_to_odom(self.odom_state, x, y, z)
        self.ax.scatter(odom_mu[0], odom_mu[1], color='g', s=25)

        self.ax.scatter(self.odom_state.x, self.odom_state.y, marker='*', color='b', s=25)
        self.ax.scatter(0.0, 0.0, marker='*', color='k', s=25)

        for name, meas_state in self.meas_states.items():
            if self.odom_state.stamp - meas_state.stamp < 1.0:
                odom_meas = self.base_link_to_odom(self.odom_state, meas_state.x, meas_state.y, meas_state.z)
                self.ax.scatter(odom_meas[0], odom_meas[1], marker='*', color='r', s=25)

        self.ax.text(odom_mu[0], odom_mu[1], label, color="black")

        self.timestamps.append(timestamp)
        self.x_vel_data.append(tfd_velocities[0])
        self.y_vel_data.append(tfd_velocities[1])
        # self.z_vel_data.append(tfd_velocities[2])
        self.ax_vel.plot(self.timestamps, self.x_vel_data, label="vx")
        self.ax_vel.plot(self.timestamps, self.y_vel_data, label="vy")
        self.ax_vel.legend(loc=2)
