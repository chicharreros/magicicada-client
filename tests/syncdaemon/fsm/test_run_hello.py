"""This is a generated python file"""
# make pylint accept this
# pylint: disable-msg=C0301
state_machine = {'events': {u'EVENT_1': [{'ACTION': u'',
                          'ACTION_FUNC': u'newline',
                          'COMMENTS': u'',
                          'PARAMETERS': {u'MV1': u'*'},
                          'STATE': {u'SV1': u'NL'},
                          'STATE_OUT': {u'SV1': u'H'}},
                         {'ACTION': u'',
                          'ACTION_FUNC': u'H',
                          'COMMENTS': u'',
                          'PARAMETERS': {u'MV1': u'*'},
                          'STATE': {u'SV1': u'H'},
                          'STATE_OUT': {u'SV1': u'E'}},
                         {'ACTION': u'',
                          'ACTION_FUNC': u'E',
                          'COMMENTS': u'',
                          'PARAMETERS': {u'MV1': u'*'},
                          'STATE': {u'SV1': u'E'},
                          'STATE_OUT': {u'SV1': u'L'}},
                         {'ACTION': u'',
                          'ACTION_FUNC': u'L',
                          'COMMENTS': u'',
                          'PARAMETERS': {u'MV1': u'1'},
                          'STATE': {u'SV1': u'L'},
                          'STATE_OUT': {u'SV1': u'L'}},
                         {'ACTION': u'',
                          'ACTION_FUNC': u'L',
                          'COMMENTS': u'',
                          'PARAMETERS': {u'MV1': u'2'},
                          'STATE': {u'SV1': u'L'},
                          'STATE_OUT': {u'SV1': u'O'}},
                         {'ACTION': u'',
                          'ACTION_FUNC': u'O',
                          'COMMENTS': u'',
                          'PARAMETERS': {u'MV1': u'1'},
                          'STATE': {u'SV1': u'O'},
                          'STATE_OUT': {u'SV1': u'W'}},
                         {'ACTION': u'',
                          'ACTION_FUNC': u'W',
                          'COMMENTS': u'',
                          'PARAMETERS': {u'MV1': u'*'},
                          'STATE': {u'SV1': u'W'},
                          'STATE_OUT': {u'SV1': u'O'}},
                         {'ACTION': u'',
                          'ACTION_FUNC': u'O',
                          'COMMENTS': u'',
                          'PARAMETERS': {u'MV1': u'2'},
                          'STATE': {u'SV1': u'O'},
                          'STATE_OUT': {u'SV1': u'R'}},
                         {'ACTION': u'NA',
                          'ACTION_FUNC': u'',
                          'COMMENTS': u'',
                          'PARAMETERS': {u'MV1': u'3'},
                          'STATE': {u'SV1': u'O'},
                          'STATE_OUT': {u'SV1': u'*'}},
                         {'ACTION': u'',
                          'ACTION_FUNC': u'R',
                          'COMMENTS': u'',
                          'PARAMETERS': {u'MV1': u'*'},
                          'STATE': {u'SV1': u'R'},
                          'STATE_OUT': {u'SV1': u'L'}},
                         {'ACTION': u'',
                          'ACTION_FUNC': u'L',
                          'COMMENTS': u'',
                          'PARAMETERS': {u'MV1': u'3'},
                          'STATE': {u'SV1': u'L'},
                          'STATE_OUT': {u'SV1': u'D'}},
                         {'ACTION': u'',
                          'ACTION_FUNC': u'D',
                          'COMMENTS': u'',
                          'PARAMETERS': {u'MV1': u'*'},
                          'STATE': {u'SV1': u'D'},
                          'STATE_OUT': {u'SV1': u'NL'}}]},
 'invalid': [],
 'parameters': {u'MV1': u'mv1 desc'},
 'state_vars': {u'SV1': u'sv1 desc'}}