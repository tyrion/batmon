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

import argparse
import collections
import enum
import logging
import json
import os
import time
import traceback


State = collections.namedtuple('State', ['pgrp', 'interval', 'charging'])


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
PGRP = os.getpgrp()

ACTIONS = dict(zip(Interval, [
    'pm-hibernate',
    CMD % (I.LOWEST.value, '-b hibernate pm-hibernate -b suspend pm-suspend'),
    CMD % (I.LOW.value, '-t warning'),
]))


def main(tries=2):
    try:
        old_state = State(**json.load(open(STATE_FILE)))
        if old_state.pgrp != PGRP:
            logging.debug('PGRP is different, discarding state')
            old_state = DEFAULT_STATE
    except (ValueError, OSError) as e:
        old_state = DEFAULT_STATE

    logging.info('old state:%s', old_state)

    B = dict(map(parse_line, open(BATTERY_FILE)))
    for k in B:
        logging.debug('%s:%s', k, B[k])


    if B['STATUS'] == 'Discharging':
        try:
            minutes = 60* (B['CHARGE_NOW']) / B['CURRENT_NOW']
        except ZeroDivisionError:
            logging.error('CURRENT_NOW is 0, could not compute remaining time')
            if tries > 1:
                logging.info('trying again in 5 seconds')
                time.seelp(5)
                return main(tries-1)
            else:
                logging.info('aborting')
                return
        logging.debug('minutes:%s', minutes)
        new_state = State(PGRP, Interval(minutes).value, False)
        logging.info('new state:%s', new_state)

        if old_state.charging or new_state.interval < old_state.interval:
            action = ACTIONS.get(new_state.interval)
            if action:
                logging.info(action)
                os.system(action)
        else:
            # do not allow battery level to increase when discharging.
            logging.debug('state.interval has not decreased')
            new_state = old_state
    else:
        new_state = State(PGRP, I.NORMAL.value, True)
        logging.info('new state:%s', new_state)

    json.dump(vars(new_state), open(STATE_FILE, 'w'))


def log_exceptions(main):
    try:
        main()
    except KeyboardInterrupt:
        logging.info('received KeyboardInterrupt, terminating')
        raise SystemExit
    except:
        for line in traceback.format_exc().splitlines():
            logging.error(line)


parser = argparse.ArgumentParser(description='Battery Monitor')
group = parser.add_mutually_exclusive_group()
group.add_argument('-q', '--quiet', action='count', default=0,
        help='decrease output verbosity')
group.add_argument('-v', '--verbosity', action='count', default=0,
        help='increase output verbosity')
parser.add_argument('-l', '--log', metavar='FILE')
parser.add_argument('-e', '--event', default='')
parser.add_argument('-p', '--poll', metavar='INTERVAL', nargs='?',
        type=int, const=60)


class PidFilter(logging.Filter):

    def filter(self, record):
        record.pid = os.getpid()
        record.pgrp = PGRP
        return True


if __name__ == '__main__':
    args = parser.parse_args()

    level = (4 + (args.quiet if args.quiet else -args.verbosity)) * 10
    logging.basicConfig(level=level, filename=args.log,
        format='[%(asctime)s] %(pgrp)s %(pid)s %(levelname)-8s %(message)s')
    logger = logging.getLogger()
    logger.addFilter(PidFilter())

    if args.poll is None:
        log_exceptions(main)
    else:
        while True:
            log_exceptions(lambda: (main(), time.sleep(args.poll)))

