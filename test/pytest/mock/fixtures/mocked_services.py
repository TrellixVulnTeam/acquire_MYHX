
##########
# This file defines all of the monkey-patching and fixtures which
# are needed to run the mocked service tests
##########

import pytest
import os
import sys
import re
import uuid

import Acquire.Service

from Acquire.Service import login_to_service_account
from Acquire.Service import _push_testing_objstore, _pop_testing_objstore
from Acquire.Service import call_function, Service

from Acquire.Identity import Authorisation, LoginSession

from Acquire.Client import User, uid_to_username
from Acquire.Crypto import OTP, PrivateKey

from admin.handler import create_handler
from identity.route import identity_functions
from accounting.route import accounting_functions
from access.route import access_functions
from storage.route import storage_functions

try:
    from pycurl import Curl as _original_Curl
except:
    _original_Curl = None

identity_handler = create_handler(identity_functions)
accounting_handler = create_handler(accounting_functions)
access_handler = create_handler(access_functions)
storage_handler = create_handler(storage_functions)


class MockedPyCurl:
    """Mocked pycurl.PyCurl class. This provides a PyCurl which calls
       the 'handler' functions of the services directly, rather
       than posting the arguments to the online services via a curl
       call. In addition, as services can call services, this also
       handles switching between the different local object stores for
       each of the services
    """
    def __init__(self):
        self._data = {}
        self._c = _original_Curl()
        # self._c.setopt(self._c.VERBOSE, True)

    URL = "URL"
    WRITEDATA = "WRITEDATA"
    POSTFIELDS = "POSTFIELDS"
    POST = "POST"
    CUSTOMREQUEST = "CUSTOMREQUEST"

    def setopt(self, typ, value):
        self._data[typ] = value
        try:
            if typ == MockedPyCurl.URL:
                self._c.setopt(self._c.URL, value)
            elif typ == MockedPyCurl.WRITEDATA:
                self._c.setopt(self._c.WRITEDATA, value)
            elif typ == MockedPyCurl.POSTFIELDS:
                self._c.setopt(self._c.POSTFIELDS, value)
            elif typ == MockedPyCurl.POST:
                self._c.setopt(self._c.POST, value)
            elif typ == MockedPyCurl.CUSTOMREQUEST:
                self._c.setopt(self._c.CUSTOMREQUEST, value)
        except:
            pass

    def perform(self):
        url = self._data["URL"]

        if url.startswith("http"):
            self._c.perform()
            return

        global _services

        if url.startswith("identity"):
            _push_testing_objstore(_services["identity"])
            func = identity_handler
        elif url.startswith("access"):
            _push_testing_objstore(_services["access"])
            func = access_handler
        elif url.startswith("accounting"):
            _push_testing_objstore(_services["accounting"])
            func = accounting_handler
        elif url.startswith("storage"):
            _push_testing_objstore(_services["storage"])
            func = storage_handler
        else:
            raise ValueError("Cannot recognise service from '%s'" % url)

        result = func(None, self._data["POSTFIELDS"])

        _pop_testing_objstore()

        if type(result) is str:
            result = result.encode("utf-8")

        self._data["WRITEDATA"].write(result)

    def getinfo(self, key):
        url = self._data["URL"]

        if url.startswith("http"):
            return self._c.getinfo(key)
        else:
            return 200

    def close(self):
        try:
            self._c.close()
        except:
            pass


# monkey-patch _pycurl.Curl so that we can mock calls
Acquire.Service._function._pycurl.Curl = MockedPyCurl

_services = {}                    # global objstore for each service


def _login_admin(service_url, username, password, otp):
    """Internal function used to get a valid login to the specified
       service for the passed username, password and otp
    """
    user = User(username=username, identity_url=service_url)

    user.request_login()
    short_uid = LoginSession.to_short_uid(user.session_uid())

    args = {"username": username,
            "short_uid": short_uid,
            "password": password,
            "otpcode": otp.generate()}

    call_function(service_url, "admin/login", args=args)

    user.wait_for_login()

    return user


@pytest.fixture(scope="module")
def aaai_services(tmpdir_factory):
    """This function creates mocked versions of all of the main services
       of the system, returning the json describing each service as
       a dictionary (which is passed to the test functions as the
       fixture)
    """
    global _services
    _services["identity"] = tmpdir_factory.mktemp("identity")
    _services["accounting"] = tmpdir_factory.mktemp("accounting")
    _services["access"] = tmpdir_factory.mktemp("access")
    _services["storage"] = tmpdir_factory.mktemp("storage")
    _services["userdata"] = tmpdir_factory.mktemp("userdata")

    password = PrivateKey.random_passphrase()
    args = {"password": password}

    responses = {}

    os.environ["SERVICE_PASSWORD"] = "Service_pa33word"
    os.environ["STORAGE_COMPARTMENT"] = str(_services["userdata"])

    args["canonical_url"] = "identity"
    args["service_type"] = "identity"
    response = call_function("identity", function="admin/setup", args=args)
    identity_service = Service.from_data(response["service"])
    identity_otp = OTP(OTP.extract_secret(response["provisioning_uri"]))
    identity_user = _login_admin("identity", "admin", password, identity_otp)
    responses["identity"] = {"service": identity_service,
                             "user": identity_user,
                             "response": response}

    args["canonical_url"] = "accounting"
    args["service_type"] = 'accounting'
    response = call_function("accounting", function="admin/setup", args=args)
    accounting_service = Service.from_data(response["service"])
    accounting_otp = OTP(OTP.extract_secret(response["provisioning_uri"]))
    accounting_user = _login_admin("accounting", "admin", password,
                                   accounting_otp)
    responses["accounting"] = {"service": accounting_service,
                               "user": accounting_user,
                               "response": response}

    args["canonical_url"] = "access"
    args["service_type"] = "access"
    response = call_function("access", function="admin/setup", args=args)
    responses["access"] = response
    access_service = Service.from_data(response["service"])
    access_otp = OTP(OTP.extract_secret(response["provisioning_uri"]))
    access_user = _login_admin("access", "admin", password, access_otp)
    responses["access"] = {"service": access_service,
                           "user": access_user,
                           "response": response}

    args["canonical_url"] = "storage"
    args["service_type"] = "storage"
    response = call_function("storage", function="admin/setup", args=args)
    storage_service = Service.from_data(response["service"])
    storage_otp = OTP(OTP.extract_secret(response["provisioning_uri"]))
    storage_user = _login_admin("storage", "admin", password, storage_otp)
    responses["storage"] = {"service": storage_service,
                            "user": storage_user,
                            "response": response}

    resource = "trust %s" % identity_service.uid()
    public_cert = identity_service.public_certificate().to_data()
    args = {"service_url": identity_service.canonical_url(),
            "authorisation": Authorisation(user=accounting_user,
                                           resource=resource).to_data(),
            "public_certificate": public_cert}

    response = call_function(accounting_service.canonical_url(),
                             function="admin/trust_service",
                             args=args, response_key=PrivateKey())

    args["authorisation"] = Authorisation(user=access_user,
                                          resource=resource).to_data()

    response = call_function(access_service.canonical_url(),
                             function="admin/trust_service",
                             args=args, response_key=PrivateKey())

    args["authorisation"] = Authorisation(user=storage_user,
                                          resource=resource).to_data()

    response = call_function(storage_service.canonical_url(),
                             function="admin/trust_service",
                             args=args, response_key=PrivateKey())

    responses["_services"] = _services

    return responses


@pytest.fixture(scope="module")
def authenticated_user(aaai_services):
    # register the new user
    username = str(uuid.uuid4())
    password = "RF%5s123!" % str(uuid.uuid4())[0:5]

    user = User(username, identity_url="identity")
    (provisioning_uri, qrcode) = user.register(password)

    otpsecret = re.search(r"secret=([\w\d+]+)&issuer",
                          provisioning_uri).groups()[0]

    user_otp = OTP(otpsecret)

    # now log the user in
    (login_url, qrcode) = user.request_login()

    assert(type(login_url) is str)

    short_uid = re.search(r"id=([\w\d+]+)",
                          login_url).groups()[0]

    args = {}
    args["short_uid"] = short_uid
    args["username"] = username
    args["password"] = password
    args["otpcode"] = user_otp.generate()

    result = call_function("identity", "login", args=args)

    assert(result["status"] == 0)

    user.wait_for_login()

    assert(user.is_logged_in())

    return user