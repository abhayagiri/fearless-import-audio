#!/usr/bin/env python

import datetime
import errno
import logging
import os
import pprint
import struct
import sys
import time
import uuid

import click
import daemonocle
import plumbum
import pytz
import yaml


CONFIG_PATH_KEYS = [
    'watch_dir',
    'queue_dir',
    'output_dir',
    'log_path',
    'pid_path',
]

logger = logging.getLogger('FearlessImportAudio')


class ImportAudio:

    def __init__(self, config, path):
        self.config = config
        self.path = path
        self.queue_path = self._make_queue_path()
        self.output_path = self._make_output_path()

    def convert(self):
        self.mkdir_p(os.path.dirname(self.queue_path))
        self.mkdir_p(os.path.dirname(self.output_path))
        logger.info('Moving %s to %s' % (self.path, self.queue_path))
        os.rename(self.path, self.queue_path)
        logger.info('Converting %s to %s' % (self.queue_path, self.output_path))
        sox = plumbum.local['sox'][
            '-V3',
            '--no-clobber',
            '--norm',
            self.queue_path,
            self.output_path,
        ]
        exit, stdout, stderr = sox.run()
        open(self.queue_path + '.log', 'w').write(stdout + stderr)
        logger.info('Conversion complete %s' % self.output_path)

    def _make_queue_path(self):
        basename = os.path.basename(self.path)
        now = datetime.datetime.now(pytz.timezone(self.config['timezone']))
        return os.path.join(
            config['queue_dir'],
            now.strftime('%m_%d_%Y_%f_') + basename
        )

    def _make_output_path(self):
        return os.path.join(
            self.config['output_dir'],
            self._path_mtime().strftime('%m_%d_%Y'),
            self._path_mtime().strftime('%m_%d_%Y') +
                '_%.3f_Raw.flac' % self._seconds_since_midnight()
            )
    def _seconds_since_midnight(self):
        now = datetime.datetime.now(pytz.timezone(self.config['timezone']))
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return (now - midnight).total_seconds()

    def _path_mtime(self):
        mt = datetime.datetime.fromtimestamp(os.path.getmtime(self.path))
        mt = mt.replace(tzinfo=pytz.utc)
        return mt.astimezone(pytz.timezone(self.config['timezone']))

    # http://stackoverflow.com/questions/600268/mkdir-p-functionality-in-python
    def mkdir_p(self, path):
        try:
            os.makedirs(path)
        except OSError as exc:  # Python >2.5
            if exc.errno == errno.EEXIST and os.path.isdir(path):
                pass
            else:
                raise


class FearlessImportAudio:

    def __init__(self, config):
        self.config = config
        self.before = None

    def loop_forever(self):
        while True:
            logger.debug('yo')
            changes = self.file_changes(self.config['watch_dir'])
            for path in changes:
                if self.is_complete(path):
                    time.sleep(1) # Wait a little bit...
                    import_audio = ImportAudio(self.config, path)
                    import_audio.convert()
                else:
                    logger.debug('Waiting for %s' % path)
            time.sleep(1)

    # def process(self, path):
        # logger.info('Start %s' % watch_path)
        # work_path = self.make_work_path(watch_path)
        # logger.info('Move %s to %s' % (watch_path, work_path))
        # os.rename(watch_path, work_path)
        # output_path = self.make_output_path(work_path)
        # logger.info('Convert %s to %s' % (work_path, output_path))
        # self.convert_wav_to_flac(work_path, output_path)
        # logger.info('End %s' % watch_path)

    def files_in_directory(self, path):
        result = {}
        for path, dirs, files in os.walk(path):
            for f in files:
                f = os.path.join(path, f)
                try:
                    result[f] = os.stat(f)
                except OSError:
                    pass
        return result

    def file_changes(self, path):
        result = []
        after = self.files_in_directory(path)
        before = self.before
        if before is not None:
            for f, after_st in after.iteritems():
                if f not in before or \
                       before[f].st_size != after_st.st_size or \
                       before[f].st_mtime != after_st.st_mtime:
                   result.append(f)
        self.before = after
        return result

    def is_complete(self, path):
        try:
            file = open(path, 'rb')
            buf = file.read(16)
            file_size = os.path.getsize(path)
        except OSError:
            return False
        if (buf[0:4] != 'RIFF') or (buf[12:16] != 'fmt '): 
            return False # not a WAV
        return struct.unpack('<L', buf[4:8])[0] + 8 == file_size


def start(config):
    logger.info('Starting...')
    instance = FearlessImportAudio(config)
    instance.loop_forever()


def shutdown():
    logger.info('Shutting down...')
    pass


def setup_logging(config):
    logging.basicConfig(
        filename=config['log_path'],
        level=getattr(logging, config['log_level']),
        format=config['log_format'],
    )


def load_config():
    base_dir = os.path.dirname(os.path.realpath(__file__))
    config = yaml.load(open(os.path.join(base_dir, 'config.yaml')))
    for key in CONFIG_PATH_KEYS:
        if not config[key].startswith('/'):
            config[key] = os.path.realpath(os.path.join(base_dir, config[key]))
    return config

if __name__ == '__main__':
    config = load_config()
    setup_logging(config)
    logger.debug('config =\n' + pprint.pformat(config))
    @click.command(cls=daemonocle.cli.DaemonCLI, daemon_params={
        'pidfile': config['pid_path'],
        'shutdown_callback': shutdown,
    })
    def wrapper():
        try:
            start(config)
        except:
            logger.exception('Uncaught exception')
    wrapper()
