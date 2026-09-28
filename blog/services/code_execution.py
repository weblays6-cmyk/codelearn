import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlparse

"""HTTP adapter for an isolated runner, never a local interpreter.

The runner accepts JSON with language, source_code, stdin, timeout_seconds,
max_output_bytes, optional function_name/test_cases, and submit. It returns
status, stdout, stderr, execution_time_ms, memory_kb, and test_results. The
runner must enforce OS/container isolation, resource limits, and test harnesses.
"""


MAX_SOURCE_BYTES = 20_000
MAX_STDIN_BYTES = 4_000
MAX_OUTPUT_BYTES = 16_000
MAX_RESPONSE_BYTES = 64_000


class CodeExecutionError(Exception):
    pass


class CodeRunnerUnavailable(CodeExecutionError):
    pass


class CodeRunnerRequestError(CodeExecutionError):
    pass


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def supported_languages():
    return tuple(
        language.strip().lower()
        for language in os.getenv('CODE_RUNNER_LANGUAGES', '').split(',')
        if language.strip()
    )


def runner_is_configured():
    runner_url = os.getenv('CODE_RUNNER_URL', '').strip()
    parsed_url = urlparse(runner_url)
    secure_scheme = parsed_url.scheme == 'https'
    local_development = parsed_url.scheme == 'http' and parsed_url.hostname in ('localhost', '127.0.0.1')
    return bool(runner_url and parsed_url.netloc and (secure_scheme or local_development) and supported_languages())


def run_code(*, source_code, language, stdin='', function_name=None, test_cases=None, submit=False):
    runner_url = os.getenv('CODE_RUNNER_URL', '').strip()
    if not runner_is_configured():
        raise CodeRunnerUnavailable('Code execution is not configured.')

    allowed_languages = supported_languages()
    language = (language or '').strip().lower()
    if not language or language not in allowed_languages:
        raise CodeRunnerRequestError('This language is not enabled for execution.')
    if not isinstance(source_code, str) or not source_code.strip():
        raise CodeRunnerRequestError('Add code before running it.')
    if len(source_code.encode('utf-8')) > MAX_SOURCE_BYTES:
        raise CodeRunnerRequestError('Code is larger than the allowed limit.')
    if not isinstance(stdin, str) or len(stdin.encode('utf-8')) > MAX_STDIN_BYTES:
        raise CodeRunnerRequestError('Input is larger than the allowed limit.')

    if test_cases is not None:
        if not isinstance(test_cases, list) or len(test_cases) > 100 or any(not isinstance(case, dict) for case in test_cases):
            raise CodeRunnerRequestError('Test configuration is invalid or too large.')

    payload = json.dumps({
        'language': language,
        'source_code': source_code,
        'stdin': stdin,
        'timeout_seconds': 5,
        'max_output_bytes': MAX_OUTPUT_BYTES,
        'function_name': function_name,
        'test_cases': test_cases or [],
        'submit': bool(submit),
    }).encode('utf-8')
    if len(payload) > 100_000:
        raise CodeRunnerRequestError('Execution request is larger than the allowed limit.')
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    api_key = os.getenv('CODE_RUNNER_API_KEY', '').strip()
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'

    request = urllib.request.Request(runner_url, data=payload, headers=headers, method='POST')
    try:
        opener = urllib.request.build_opener(_RejectRedirects())
        with opener.open(request, timeout=8) as response:
            response_body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(response_body) > MAX_RESPONSE_BYTES:
            raise CodeRunnerRequestError('Execution service returned an oversized response.')
        result = json.loads(response_body.decode('utf-8'))
    except urllib.error.HTTPError as error:
        raise CodeRunnerRequestError('Execution service rejected the request.') from error
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise CodeRunnerUnavailable('Execution service could not be reached.') from error

    if not isinstance(result, dict):
        raise CodeRunnerRequestError('Execution service returned an invalid response.')

    stdout = str(result.get('stdout', ''))[:MAX_OUTPUT_BYTES]
    stderr = str(result.get('stderr', ''))[:MAX_OUTPUT_BYTES]
    status = str(result.get('status', 'INTERNAL_ERROR')).upper()
    valid_statuses = {
        'SUCCESS', 'ACCEPTED', 'WRONG_ANSWER', 'RUNTIME_ERROR',
        'COMPILATION_ERROR', 'TIME_LIMIT_EXCEEDED', 'INTERNAL_ERROR',
    }
    if status not in valid_statuses:
        status = 'INTERNAL_ERROR'

    test_results = result.get('test_results', [])
    if not isinstance(test_results, list):
        test_results = []
    safe_test_results = []
    for test_result in test_results[:100]:
        if not isinstance(test_result, dict):
            continue
        hidden = bool(test_result.get('hidden'))
        safe_test_results.append({
            'passed': bool(test_result.get('passed')),
            'input': '' if hidden else str(test_result.get('input', ''))[:2_000],
            'expected': '' if hidden else str(test_result.get('expected', ''))[:2_000],
            'actual': '' if hidden else str(test_result.get('actual', ''))[:2_000],
            'hidden': hidden,
        })

    def bounded_number(value, maximum):
        if isinstance(value, bool) or value is None:
            return None
        try:
            number = int(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return number if 0 <= number <= maximum else None

    return {
        'status': status,
        'stdout': stdout,
        'stderr': stderr,
        'execution_time_ms': bounded_number(result.get('execution_time_ms'), 3_600_000),
        'memory_kb': bounded_number(result.get('memory_kb'), 10_000_000),
        'test_results': safe_test_results,
    }
