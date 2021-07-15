from Acquire.Identity import Authorisation, AuthorisationError
from Acquire.Access import RunRequest, WorkSheet
from Acquire.Client import Cheque

from typing import Dict


def run(args: Dict) -> Dict:
    """This function is used to handle requests to run compute jobs using
    the system. This will be passed in the RunRequest with a valid
    authorisation and also a Cheque to pay for the calculation.

    This will return the UID of the running job plus the location
    to which the output will be written

    Args:
        args: Dictionary of arguments
    Returns:
        dict: Dictionary of job details
    """
    request = None
    authorisation = None
    cheque = None

    if "request" in args:
        request = RunRequest.from_data(args["request"])

    if "authorisation" in args:
        authorisation = Authorisation.from_data(args["authorisation"])

    if "cheque" in args:
        cheque = Cheque.from_data(args["cheque"])

    if request is None:
        return

    if authorisation is None:
        raise AuthorisationError(f"You must provide a valid authorisation to make the request {str(request)}")

    if cheque is None:
        raise AuthorisationError(f"You must provide a valid cheque to pay for the request {str(request)}")

    # create a job sheet to record all stages of the job
    worksheet = WorkSheet(request=request, authorisation=authorisation)

    # submit the job, recording everything necessary to the JobSheet
    worksheet.execute(cheque=cheque)

    # Return to the user the UID of the job and also the location
    # to which all output from the job is being written
    return {"uid": worksheet.uid(), "output": worksheet.output_location().to_string()}
