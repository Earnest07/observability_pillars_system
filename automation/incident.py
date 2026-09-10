call_attempts = 0


def start_incident(alert):

    global call_attempts

    while call_attempts < 5:

        call_attempts += 1

        answered = trigger_call()

        if answered:
            print("Engineer acknowledged alert")
            return


    print("No response after 5 calls")

    trigger_terraform_scale()
