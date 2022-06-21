"""This is a generated python file"""

from __future__ import unicode_literals

state_machine = {'events': {'EVENT_1': [{'ACTION': '',
                          'ACTION_FUNC': 'newline',
                          'COMMENTS': '',
                          'PARAMETERS': {'MV1': '*'},
                          'STATE': {'SV1': 'NL'},
                          'STATE_OUT': {'SV1': 'H'}},
                         {'ACTION': '',
                          'ACTION_FUNC': 'H',
                          'COMMENTS': '',
                          'PARAMETERS': {'MV1': '*'},
                          'STATE': {'SV1': 'H'},
                          'STATE_OUT': {'SV1': 'E'}},
                         {'ACTION': '',
                          'ACTION_FUNC': 'E',
                          'COMMENTS': '',
                          'PARAMETERS': {'MV1': '*'},
                          'STATE': {'SV1': 'E'},
                          'STATE_OUT': {'SV1': 'L'}},
                         {'ACTION': '',
                          'ACTION_FUNC': 'L',
                          'COMMENTS': '',
                          'PARAMETERS': {'MV1': '1'},
                          'STATE': {'SV1': 'L'},
                          'STATE_OUT': {'SV1': 'L'}},
                         {'ACTION': '',
                          'ACTION_FUNC': 'L',
                          'COMMENTS': '',
                          'PARAMETERS': {'MV1': '2'},
                          'STATE': {'SV1': 'L'},
                          'STATE_OUT': {'SV1': 'O'}},
                         {'ACTION': '',
                          'ACTION_FUNC': 'O',
                          'COMMENTS': '',
                          'PARAMETERS': {'MV1': '1'},
                          'STATE': {'SV1': 'O'},
                          'STATE_OUT': {'SV1': 'W'}},
                         {'ACTION': '',
                          'ACTION_FUNC': 'W',
                          'COMMENTS': '',
                          'PARAMETERS': {'MV1': '*'},
                          'STATE': {'SV1': 'W'},
                          'STATE_OUT': {'SV1': 'O'}},
                         {'ACTION': '',
                          'ACTION_FUNC': 'O',
                          'COMMENTS': '',
                          'PARAMETERS': {'MV1': '2'},
                          'STATE': {'SV1': 'O'},
                          'STATE_OUT': {'SV1': 'R'}},
                         {'ACTION': 'NA',
                          'ACTION_FUNC': '',
                          'COMMENTS': '',
                          'PARAMETERS': {'MV1': '3'},
                          'STATE': {'SV1': 'O'},
                          'STATE_OUT': {'SV1': '*'}},
                         {'ACTION': '',
                          'ACTION_FUNC': 'R',
                          'COMMENTS': '',
                          'PARAMETERS': {'MV1': '*'},
                          'STATE': {'SV1': 'R'},
                          'STATE_OUT': {'SV1': 'L'}},
                         {'ACTION': '',
                          'ACTION_FUNC': 'L',
                          'COMMENTS': '',
                          'PARAMETERS': {'MV1': '3'},
                          'STATE': {'SV1': 'L'},
                          'STATE_OUT': {'SV1': 'D'}},
                         {'ACTION': '',
                          'ACTION_FUNC': 'D',
                          'COMMENTS': '',
                          'PARAMETERS': {'MV1': '*'},
                          'STATE': {'SV1': 'D'},
                          'STATE_OUT': {'SV1': 'NL'}}]},
 'invalid': [],
 'parameters': {'MV1': 'mv1 desc'},
 'state_vars': {'SV1': 'sv1 desc'}}