"""Allow-listed creation diagnostics; never render provider-controlled text."""
import re
import sys


class MalformedSessionResponse(Exception):
    pass


def classify(error):
    # Import only during execution; offline preflight does not require the SDK.
    import openai
    names = ('BadRequestError', 'AuthenticationError', 'PermissionDeniedError',
             'NotFoundError', 'ConflictError', 'UnprocessableEntityError',
             'RateLimitError', 'InternalServerError', 'APIStatusError',
             'APITimeoutError', 'APIConnectionError', 'APIResponseValidationError')
    allowed = {getattr(openai, name): name for name in names}
    kind = allowed.get(type(error), 'UNKNOWN')
    if type(error) is MalformedSessionResponse:
        kind = 'MALFORMED_SESSION_RESPONSE'
    result = {'phase': 'SESSION_CREATE', 'category': kind}
    # Do not inspect arbitrary exception properties or accept bool/string status.
    if type(error) in allowed and isinstance(error, openai.APIStatusError):
        status = vars(error).get('status_code')
        if type(status) is int and 400 <= status <= 599:
            result['http_status'] = status
    return result


def create_session(client, request, state):
    print('PILOT_PHASE SESSION_CREATE START', file=sys.stderr, flush=True)
    try:
        session = client.beta.agents.sessions.create(**request)
        sid = getattr(session, 'id', None)
        # Match the existing recovery identifier contract, without a guessed prefix.
        if type(sid) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', sid):
            raise MalformedSessionResponse()
    except BaseException as error:
        diagnostic = classify(error)
        state['creation_diagnostic'] = diagnostic
        suffix = (' HTTP_' + str(diagnostic['http_status'])) if 'http_status' in diagnostic else ''
        print('PILOT_PHASE SESSION_CREATE BLOCKED ' + diagnostic['category'] + suffix,
              file=sys.stderr, flush=True)
        raise
    print('PILOT_PHASE SESSION_CREATE COMPLETE', file=sys.stderr, flush=True)
    return session
