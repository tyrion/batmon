#!/usr/bin/env python3

# Copyright (C) 2015  Germano Gabbianelli
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import collections
import enum
import logging
import json
import os


logging.basicConfig(level=logging.DEBUG)

State = collections.namedtuple('State', ['ppid', 'interval', 'charging'])

class Interval(float, enum.Enum):
    CRITICAL = 1.30
    LOWEST = 5
    LOW = 20
    NORMAL = 60*12


def new(cls, m):
    for interval in cls:
        if m <= interval:
            return interval
    return Interval.NORMAL

Interval.__new__ = new
I = Interval

def parse_line(line):
    line = line.strip().replace('POWER_SUPPLY_', '')
    key, value = line.split('=')
    return key, int(value) if value.isdigit() else value



STATE_FILE = '/tmp/battery.json'
BATTERY_FILE = '/sys/class/power_supply/BAT0/uevent'
DEFAULT_STATE = State(None, Interval.NORMAL, True)
CMD = "i3-nagbar -m 'Less than %d minutes of battery remaining!' %s"
PPID = os.getppid()

ACTIONS = dict(zip(Interval, [
    'pm-hibernate',
    CMD % (I.LOWEST.value, '-b hibernate pm-hibernate -b suspend pm-suspend'),
    CMD % (I.LOW.value, '-t warning'),
]))


try:
    old_state = State(**json.load(open(STATE_FILE)))
    if old_state.ppid != PPID:
        logging.debug('PPID is different, discarding state')
        old_state = DEFAULT_STATE
except (ValueError, OSError) as e:
    old_state = DEFAULT_STATE

logging.info('old state:%s', old_state)

B = dict(map(parse_line, open(BATTERY_FILE)))
for k in B:
    logging.debug('%s:%s', k, B[k])


if B['STATUS'] == 'Discharging':
    minutes = 60* (B['CHARGE_NOW']) / B['CURRENT_NOW']
    logging.debug('minutes:%s', minutes)
    new_state = State(PPID, Interval(minutes).value, False)
    logging.info('new state:%s', new_state)

    if old_state.charging or new_state.interval < old_state.interval:
        action = ACTIONS.get(new_state.interval)
        logging.info(action)
        os.system(action)
    else:
        # do not allow battery level to increase when discharging.
        logging.debug('state.interval has not decreased')
        new_state = old_state
else:
    new_state = State(PPID, I.NORMAL.value, True)
    logging.info('new state:%s', new_state)

json.dump(vars(new_state), open(STATE_FILE, 'w'))
