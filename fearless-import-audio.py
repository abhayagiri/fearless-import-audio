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
import portalocker
import pytz
import taglib
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
        self.path_mtime = self._get_path_mtime()
        self.queue_path = self._make_queue_path()
        self.output_path = None

    def convert(self):
        self.mkdir_p(os.path.dirname(self.queue_path))
        logger.info('Moving %s to %s' % (self.path, self.queue_path))
        os.rename(self.path, self.queue_path)
        self.output_path = self._make_output_path()
        logger.info('Converting %s to %s' % (self.queue_path, self.output_path))
        os.unlink(self.output_path)
        sox = plumbum.local['sox'][
            '-V3',
            '--no-clobber',
            '--norm',
            self.queue_path,
            self.output_path,
        ]
        exit, stdout, stderr = sox.run()
        open(self.queue_path + '.log', 'w').write(stdout + stderr)
        file = taglib.File(self.output_path)
        file.tags[u'ALBUM'] = [self.tag_album()]
        file.tags[u'YEAR'] = [self.tag_year()]
        file.tags[u'DATE'] = [self.tag_date()]
        # This should be COMMENT but a bug in audacity requires it to be COMMENT?
        file.tags[u'COMMENTS'] = [self.tag_comment()]
        file.tags[u'GENRE'] = [u'Dhamma Talks']
        file.save()
        logger.info('Conversion complete %s' % self.output_path)

    def tag_album(self):
        return u'{dt.year} Abhayagiri Dhamma Talks'.format(
            dt=self.path_mtime)

    def tag_year(self):
        return unicode(self.path_mtime.strftime('%Y'))

    def tag_date(self):
        return unicode(self.path_mtime.strftime('%Y-%m-%d'))

    def tag_comment(self):
        return (u'This talk was offered on {dt:%B} {dt.day}, {dt.year}' +
            u' at Abhayagiri Buddhist Monastery.').format(
            dt=self.path_mtime)

    def _make_queue_path(self):
        basename = os.path.basename(self.path)
        now = datetime.datetime.now(pytz.timezone(self.config['timezone']))
        return os.path.join(
            config['queue_dir'],
            now.strftime('%Y-%m-%d %H%M%S ') + basename
        )

    def _make_output_path(self):
        base_dir = os.path.join(
            self.config['output_dir'],
            self.path_mtime.strftime('%Y-%m-%d')
        )
        self.mkdir_p(base_dir)
        tries = 0
        while True:
            if tries > 0:
                try_str = '%d ' % tries
            else:
                try_str = ''
            path = os.path.join(base_dir,
                self.path_mtime.strftime('%Y-%m-%d ') + try_str + 'Raw.flac'
            )
            if os.path.exists(path):
                logger.debug('File already exists %s, trying another...' % path)
                tries += 1
            else:
                open(path, 'wb').write('')
                return path

    def _seconds_since_midnight(self):
        now = datetime.datetime.now(pytz.timezone(self.config['timezone']))
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return (now - midnight).total_seconds()

    def _get_path_mtime(self):
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
            try:
                self.process()
            except Exception as e:
                logger.error('Got exception %s' % e)
            time.sleep(1)

    def process(self):
        for path in self.files_in_directory(self.config['watch_dir']):
            if path.lower().endswith('.wav'):
                if self.wav_is_complete(path):
                    time.sleep(1) # Wait a little bit...
                    import_audio = ImportAudio(self.config, path)
                    import_audio.convert()
                else:
                    logger.debug('Waiting for %s' % path)
            else:
                # Ignore
                pass

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

    def wav_is_complete(self, path):
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


def shutdown(message, code):
    logger.info('Shutting down...')
    logger.debug(message)


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
        except SystemExit:
            pass
        except:
            logger.exception('Uncaught exception')
    wrapper()
