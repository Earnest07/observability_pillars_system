import boto3
import os


REGION = os.getenv(
    "AWS_DEFAULT_REGION",
    "ap-south-1"
)

ASG_NAME = "observability-autoscaling-application-asg"


autoscaling = boto3.client(
    "autoscaling",
    region_name=REGION
)


def get_asg_state():

    response = autoscaling.describe_auto_scaling_groups(
        AutoScalingGroupNames=[ASG_NAME]
    )

    asg = response["AutoScalingGroups"][0]

    return {
        "min": asg["MinSize"],
        "max": asg["MaxSize"],
        "desired": asg["DesiredCapacity"],
        "instances": len(asg["Instances"])
    }


def scale_out():

    print("=" * 60)
    print("AWS SCALE OUT CHECK")
    print("=" * 60)

    state = get_asg_state()

    min_size = state["min"]
    max_size = state["max"]
    desired = state["desired"]

    print("Min:", min_size)
    print("Max:", max_size)
    print("Desired:", desired)

    # Already at maximum capacity.
    if desired >= max_size:

        print(
            "Scale-out skipped: "
            "desired capacity is already at maximum."
        )

        return {
            "action": "none",
            "reason": "maximum_capacity_reached",
            "desired": desired,
            "max": max_size
        }

    new_desired = desired + 1

    autoscaling.set_desired_capacity(
        AutoScalingGroupName=ASG_NAME,
        DesiredCapacity=new_desired,
        HonorCooldown=True
    )

    print(
        f"Desired capacity changed: "
        f"{desired} -> {new_desired}"
    )

    return {
        "action": "scale_out",
        "old_desired": desired,
        "new_desired": new_desired,
        "max": max_size
    }


def scale_in():

    print("=" * 60)
    print("AWS SCALE IN CHECK")
    print("=" * 60)

    state = get_asg_state()

    min_size = state["min"]
    max_size = state["max"]
    desired = state["desired"]

    print("Min:", min_size)
    print("Max:", max_size)
    print("Desired:", desired)

    # Already at minimum capacity.
    if desired <= min_size:

        print(
            "Scale-in skipped: "
            "desired capacity is already at minimum."
        )

        return {
            "action": "none",
            "reason": "minimum_capacity_reached",
            "desired": desired,
            "min": min_size
        }

    new_desired = desired - 1

    autoscaling.set_desired_capacity(
        AutoScalingGroupName=ASG_NAME,
        DesiredCapacity=new_desired,
        HonorCooldown=True
    )

    print(
        f"Desired capacity changed: "
        f"{desired} -> {new_desired}"
    )

    return {
        "action": "scale_in",
        "old_desired": desired,
        "new_desired": new_desired,
        "min": min_size
    }
