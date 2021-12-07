import math
import rospy
import actionlib
from geometry_msgs.msg import PoseStamped

from move_base_msgs.msg import MoveBaseAction, MoveBaseGoal, MoveBaseResult

from smach import State, StateMachine

class GoToWaypointState(State):
    def __init__(self):
        super(GoToWaypointState, self).__init__(
            outcomes=["success", "preempted", "failure", "finished"],
            input_keys=["waypoints_plan", "waypoint_index_in", "state_machine"],
            output_keys=["waypoints_plan", "waypoint_index_out", "state_machine"]
        )
        self.reset()
    
    def reset(self):
        self.action_result = "success"
        self.goal_pose_stamped = None
        self.current_waypoint_index = 0
        self.num_waypoints = 0

        self.action_server = None
        self.move_base = None

        self.intermediate_tolerance = 0.0
        self.ignore_orientation = False

        self.intermediate_settle_time = rospy.Duration(0.25)  # TODO: change to launch param or goal param
        self.within_range_time = None
        
        self.is_move_base_done = False
        self.distance_to_goal = 0.0
        
    def execute(self, userdata):
        self.reset()

        self.action_result = "success"
        self.action_server = userdata.state_machine.action_server
        self.action_goal = userdata.state_machine.action_goal
        self.move_base = userdata.state_machine.move_base

        self.num_waypoints = len(userdata.waypoints_plan)
        self.current_waypoint_index = userdata.waypoint_index_in

        rospy.loginfo("Number of waypoints: %s, Current index: %s" % (self.num_waypoints, self.current_waypoint_index))

        if userdata.waypoint_index_in >= self.num_waypoints:
            self.action_server.set_succeeded()
            return "finished"
        
        waypoint, pose_array = userdata.waypoints_plan[userdata.waypoint_index_in]

        self.intermediate_tolerance = waypoint.intermediate_tolerance
        self.ignore_orientation = waypoint.ignore_orientation

        if self.ignore_orientation:
            self.intermediate_tolerance = 0.075  # TODO: pull this from move_base local planner parameters
        
        self.goal_pose_stamped = PoseStamped()
        self.goal_pose_stamped.header = pose_array.header
        self.goal_pose_stamped.pose = pose_array.poses[-1]

        # forked version of move_base: https://github.com/frc-88/navigation
        # In this version, move_base accepts pose arrays. If continuous mode is enabled,
        # waypoints are all used together in the global plan instead of discrete move_base
        # action calls
        goal = MoveBaseGoal()
        goal.target_poses.header.frame_id = pose_array.header.frame_id
        goal.target_poses = pose_array
        
        rospy.loginfo("Going to position (%s, %s)" % (self.goal_pose_stamped.pose.position.x, self.goal_pose_stamped.pose.position.y))

        self.move_base.send_goal(goal, feedback_cb=self.move_base_feedback, done_cb=self.move_base_done)
        self.wait_for_move_base()

        if self.action_result != "success":
            return self.action_result

        move_base_result = self.move_base.get_result()
        if bool(move_base_result):
            userdata.waypoint_index_out = userdata.waypoint_index_in + 1
            return "success"
        else:
            rospy.loginfo("move_base result was not a success")
            return "failure"

    def wait_for_move_base(self):
        rate = rospy.Rate(10.0)
        while not self.is_move_base_done:
            if rospy.is_shutdown():
                rospy.loginfo("Received abort. Cancelling waypoint goal")
                self.action_server.set_aborted()
                self.action_result = "failure"
                self.move_base.cancel_goal()
                break

            if self.action_server.is_preempt_requested():
                rospy.loginfo("Received preempt. Cancelling waypoint goal")
                self.action_server.set_preempted()
                self.action_result = "preempted"
                self.move_base.cancel_goal()
                break

            # if ignore_orientation is True
            #   if this is the last waypoint
            #       wait for the robot to settle, then cancel goal
            #   if this isn't the last waypoint
            #       cancel goal
            # if ignore_orientation is False
            #   if intermediate_tolerance is greater than zero
            #       cancel goal

            if self.distance_to_goal <= self.intermediate_tolerance:
                if self.within_range_time is None:
                    self.within_range_time = rospy.Time.now()

                if self.ignore_orientation:
                    if self.current_waypoint_index < self.num_waypoints - 1:
                        if rospy.Time.now() - self.within_range_time > self.intermediate_settle_time:
                            self.close_enough_to_goal()
                    else:
                        self.close_enough_to_goal()
                else:
                    if self.intermediate_tolerance > 0.0:
                        self.close_enough_to_goal()
            else:
                self.within_range_time = None
            
            rate.sleep()
        
    def move_base_feedback(self, feedback):
        self.distance_to_goal = self.get_xy_dist(feedback.base_position, self.goal_pose_stamped)

    def close_enough_to_goal(self):
        rospy.loginfo("Robot is close enough to goal. Moving on")
        self.move_base.cancel_goal()
        self.action_result = "success"
    
    def move_base_done(self, goal_status, result):
        rospy.loginfo("move_base finished")
        self.is_move_base_done = True
    
    def get_xy_dist(self, pose1, pose2):
        # pose1 and pose2 are PoseStamped
        x1 = pose1.pose.position.x
        y1 = pose1.pose.position.y
        x2 = pose2.pose.position.x
        y2 = pose2.pose.position.y
        
        dx = x2 - x1
        dy = y2 - y1

        return math.sqrt(dx * dx + dy * dy)


class WaypointStateMachine(object):
    def __init__(self):
        self.sm = StateMachine(outcomes=["success", "failure", "preempted"])
        self.outcome = None
        self.action_server = None
        self.action_goal = None

        self.move_base_namespace = rospy.get_param("~move_base_namespace", "/move_base")
        self.move_base = actionlib.SimpleActionClient(self.move_base_namespace, MoveBaseAction)

        with self.sm:
            StateMachine.add(
                "GOTO_WAYPOINT", GoToWaypointState(),
                transitions={
                    "success": "GOTO_WAYPOINT",
                    "finished": "success",
                    "failure": "failure",
                    "preempted": "preempted"
                },
                remapping={
                    "waypoints_plan": "sm_waypoints_plan",
                    "waypoint_index_in": "sm_waypoint_index",
                    "waypoint_index_out": "sm_waypoint_index",
                    "state_machine": "sm_state_machine",
                }
            )

    def execute(self, waypoints_plan, action_server):
        rospy.loginfo("Connecting to move_base...")
        self.move_base.wait_for_server()
        rospy.loginfo("move_base connected")

        rospy.loginfo("To cancel the waypoint follower, run: 'rostopic pub -1 /tj2/follow_path/cancel actionlib_msgs/GoalID -- {}'")
        rospy.loginfo("To cancel the current goal, run: 'rostopic pub -1 /move_base/cancel actionlib_msgs/GoalID -- {}'")

        self.action_server = action_server

        self.sm.userdata.sm_waypoint_index = 0
        self.sm.userdata.sm_waypoints_plan = waypoints_plan
        self.sm.userdata.sm_state_machine = self
        self.outcome = self.sm.execute()
        return self.outcome