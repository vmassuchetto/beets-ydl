# -*- coding: utf-8 -*-
# Copyright 2016, Vinicius Massuchetto.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

from beets import config
from beets import ui
from beets.plugins import BeetsPlugin
from optparse import OptionParser
from pathlib import Path
from shutil import copyfile
from xdg import BaseDirectory
from yt_dlp import YoutubeDL
from hashlib import md5
import glob
import json
import os
import re
import shutil
import subprocess
import uuid

class Colors():
    INFO = '\033[94m'
    SUCCESS = '\033[92m'
    WARNING = '\033[93m'
    BOLD = '\033[1m'
    END = '\033[0m'

class YdlPlugin(BeetsPlugin):
    """A plugin for downloading music from YouTube and importing into beets.

    It tries to split album files if it can identify track times somewhere.
    """
    def __init__(self, *args, **kwargs):
        """Set default values

        `self.config['youtubedl_options']` is a dict with a lot of options
        available from youtube-dl: https://git.io/fN0c7
        """
        super(YdlPlugin, self).__init__()

        self.search_query = "https://www.youtube.com/results?search_query="
        self.config_dir = config.config_dir()
        self.cache_dir = self.config_dir + "/ydl-cache"
        self.outtmpl = self.cache_dir + "/%(id)s/%(id)s.%(ext)s"

        # Default options
        self._config = {
            'urls': [],
            'verbose': False,
            'youtubedl_options': {
                'verbose': False,
                'keepvideo': False,
                'cachedir': self.cache_dir,
                'outtmpl': self.outtmpl,
                'restrictfilenames': True,
                'ignoreerrors': True,
                'nooverwrites': True,
                'writethumbnail': True,
                'quiet': True,
                'usenetrc': os.path.exists(
                    os.path.join(str(Path.home()), ".netrc")),
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                    'nopostoverwrites': True
                }]
            }
        }
        self._config.update(self.config)
        self.config = self._config

        # be verbose if beets is verbose
        if not self.config.get('verbose'):
            self.config['verbose'] = True

    def commands(self):
        outer_class = self

        def ydl_func(lib, opts, args):
            """Parse args and download one source at a time to pass it to
            beets
            """
            for opt, value in opts.__dict__.items():
                self.config[opt] = value

            if len(args) > 0:
                for arg in args:
                    outer_class.youtubedl(lib, opts, arg)
            elif self.config.get('urls') is not None:
                if self.config.get('verbose'):
                    print("[ydl] Falling back to default urls")
                for url in self.config.get('urls'):
                    outer_class.youtubedl(lib, opts, str(url))

        parser = OptionParser()
        parser.add_option("--no-download", action="store_false",
            default=True, dest="download", help="don't actually " + \
                "download files, only the descriptions")
        parser.add_option("--no-split-files", action="store_false",
            default=True, dest="split_files", help="don't try " + \
                "to split files when an album is identified")
        parser.add_option("--no-import", action="store_false",
            default=True, dest="import", help="do not import into " + \
                "beets after downloading and processing")
        parser.add_option("-f", "--force-download", action="store_true",
            default=False, dest="force_download", help="always download " + \
                "and overwrite files")
        parser.add_option("-k", "--keep-files", action="store_true",
            default=False, dest="keep_files", help="keep the files " + \
                "downloaded on cache, useful for caching or bulk importing")
        parser.add_option("-w", "--write-dummy-mp3", action="store_true",
            default=False, dest="write_dummy_mp3", help="write blank " + \
                "dummy mp3 files with valid ID3 information")
        parser.add_option("-v", "--verbose", action="store_true",
            dest="verbose", default=False, help="print processing " + \
                "information")

        ydl_cmd = ui.Subcommand('ydl', parser=parser,
            help=u'Download music from YouTube')
        ydl_cmd.func = ydl_func

        return [ydl_cmd]

    def youtubedl(self, lib, opts, arg):
        """Calls YoutubeDL

        Call beets when finishes downloading the audio file. We don't implement
        a YoutubeDL's post processor because we want to call beets for every
        download, and not after downloading a lot of files.

        So we try to read `YoutubeDL.extract_info` entries and process them
        with an internal `YoutubeDL.process_ie_result` method, that will
        actually download the audio file.
        """
        if self.config.get('verbose'):
            print("[ydl] Calling youtube-dl")

        youtubedl_config = self.config.get('youtubedl_options')
        youtubedl_config['keepvideo'] = self.config.get('keep_files')
        y = YoutubeDL(youtubedl_config)

        ie_result = y.extract_info(arg, download=False, process=False)

        if ie_result is None:
            print("[ydl] Error: Failed to fetch file information.")
            print("[ydl]   If this is not a network problem, try upgrading")
            print("[ydl]   beets-ydl:")
            print("[ydl]")
            print("[ydl]     pip install -U beets-ydl")
            print("[ydl]")
            exit(1)

        if 'entries' in ie_result:
            entries = ie_result['entries']
        else:
            entries = [ie_result]

        download = self.config.get('download')
        if self.config.get('force_download'):
            download = True

        for entry in entries:
            items = [x for x in lib.items('ydl:' + entry['id'])] + \
                [x for x in lib.albums('ydl:' + entry['id'])]

            if len(items) > 0 and not self.config.get('force_download'):
                if self.config.get('verbose'):
                    print('[ydl] Skipping item already in library:' + \
                        ' %s [%s]' % (entry['title'], entry['id']))
                continue

            if self.config.get('verbose') and not download:
                print("[ydl] Skipping download: " + entry['id'])

            data = y.process_ie_result(entry, download=download)
            if data:
                ie_result.update(data)
                self.info = ie_result
                self.process_item()
            else:
                print("[ydl] No data for " + entry['id'])

    def is_in_library(self, entry, lib):
        """Check if an `entry` is already in the `lib` beets library
        """
        if lib.items(('ydl_id', entry['id'])):
            return True
        else:
            return False

    def get_file_path(self, ext):
        return self.outtmpl % { 'id': self.info.get('id'), 'ext': ext }

    def is_album(self):
        return self.fullalbum_stripped or len(self.tracks) > 1

    def process_item(self):
        """Called after downloading source with YoutubeDL

        From here on, the plugin assumes its state according to what
        is being downloaded.
        """
        print('[ydl] Processing item: ' + self.info.get('title'))

        ext = self.config.get('youtubedl_options')\
                ['postprocessors'][0]['preferredcodec']
        self.audio_file = self.get_file_path(ext)
        self.outdir, self.audio_file_ext = os.path.splitext(self.audio_file)
        self.outdir = os.path.dirname(self.outdir)

        if self.config.get('verbose') and \
            self.config.get('download') and \
            not os.path.exists(self.audio_file):
            print('[ydl] Error: Audio file not found: ' + self.audio_file)
            exit(1)

        self.strip_fullalbum()
        self.extract_tracks()

        if not self.is_album():
            self.set_single_file_data()

        if self.config.get('verbose'):
            print(self.get_tracklist())

        if self.config.get('write_dummy_mp3'):
            self.write_dummy_mp3()

        if self.config.get('verbose') and self.is_album():
            print("[ydl] URL is identified as an album")
        else:
            print("[ydl] URL is identified as a singleton")

        if self.config.get('split_files') \
            and not self.config.get('write_dummy_mp3') \
            and self.is_album():
            self.split_file()

        if self.config.get('import'):
            beet_cmd = self.get_beet_cmd()
            if self.config.get('verbose'):
                print("[ydl] Running beets: " + ' '.join(beet_cmd))
            subprocess.run(beet_cmd)
        elif self.config.get('verbose'):
            print('[ydl] Skipping import')

        if not self.config.get('keep_files'):
            self.clean()
        elif self.config.get('verbose') and self.config.get('keep_files'):
            print('[ydl] Keeping downloaded files on ' + self.outdir)

    def get_beet_cmd(self):
        beet_cmd = ['beet']

        if os.getenv('BEETS_ENV') == 'develop':
            beet_cmd.extend(['-c', 'env.config.yml'])

        if self.config.get('verbose'):
            beet_cmd.extend(['-v'])

        beet_cmd.extend(['import', '--set', 'ydl=' + self.info.get('id')])

        if not self.is_album():
            beet_cmd.extend(['--singletons'])

        if os.path.exists(self.outdir):
            beet_cmd.extend([self.outdir])
        else:
            beet_cmd.extend([self.audio_file])

        return beet_cmd

    def __exit__(self, exc_type, exc_value, traceback):
        cache_size = self.config.get('cache_dir')
        if cache_size > 0:
            print("[ydl] " + cache_size + " in cache")

        if self.config.get('verbose'):
            print('[ydl] Leaving')

    def clean(self):
        """Deletes everything related to the present run.
        """
        files = glob.glob(self.outdir + '*')
        for f in files:
            if os.path.isdir(f):
                shutil.rmtree(f)
            else:
                os.remove(f)

    def strip_fullalbum(self):
        """Will remove '[Full Album]' entries on video title.
        """
        regex = re.compile(r'\S*?(fullalbum|full[^a-z]+album|album)\S*?',
            re.IGNORECASE)
        title = regex.sub('', self.info.get('title'))
        if title != self.info.get('title'):
            self.info['title'] = title
            self.fullalbum_stripped = True

        self.fullalbum_stripped = False

    def split_file(self):
        """Split downloaded file into multiple tracks

        Tries to parse metadata from the video description.
        """
        # @TODO check for overwrites according to options

        if self.config.get('verbose'):
            print("[ydl] Splitting tracks")

        cmds = []
        ffmpeg_cmd = ['ffmpeg', '-y', '-i', self.audio_file,
            '-acodec', 'copy']

        if not os.path.exists(self.outdir):
            os.mkdir(self.outdir)

        file_id = os.path.basename(os.path.normpath(self.outdir))

        for track in self.tracks:
            opts = ['-ss', str(track['start']), '-to', str(track['end'])]

            for k in track.keys():
                opts.extend(['-metadata', '%s=%s' % (k, track[k])])

            outfile = '%s/%03d-%s%s' % (self.outdir,
                track['track'], file_id, self.audio_file_ext)
            opts.extend([outfile])

            cmds.append(ffmpeg_cmd + opts)

        if len(cmds) > 0 and os.path.exists(self.audio_file):
            print("[ydl] Running ffmpeg")
            for cmd in cmds:
                subprocess.run(cmd, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)
            os.remove(self.audio_file)

    def clean_str(self, s):
        s = re.sub(r'[^0-9a-zA-Z ]', '', s)
        s = re.sub(r'\s+', ' ', s)
        s = s.strip()

        return s

    def get_common_metadata(self):
        """Tries to translate metadata parsed from video description into file
        metadata.

        Will also remove years from title.
        """
        metadata = {}

        year = self.get_year()
        if year is not None:
            metadata['year'] = year

        metadata['artist'], metadata['album'] = self.parse_title()

        return metadata

    def get_year(self):
        year_regex = r'[^\S]?([12][0-9]{3})[^\S]?'
        regex = re.compile(year_regex)
        matches = regex.match(self.info.get('title'))
        if matches:
            self.info['title'] = re.sub(year_regex, '', self.info['title'])
            year = matches.group(1)
            return year

        return None

    def parse_title(self):
        """Parse the title trying to find an "Artist - Album" pattern
        """
        seps_regex = r'(.*?)[-~|*%#](.*)'
        regex = re.compile(seps_regex)

        if regex.match(self.info.get('title')):
            art_alb = regex.findall(self.info.get('title'))
            first = art_alb[0][0]
            second = art_alb[0][1]

        # in beets we trust
        else:
            first = self.info.get('title')
            second = self.info.get('title')

        return (self.clean_str(first), self.clean_str(second))

    def to_seconds(self, time):
        """Convert MM:SS to seconds
        """
        secs = 0
        parts = [int(s) for s in time.split(':')]
        secs = parts[len(parts)-1]
        secs += parts[len(parts)-2] * 60
        if len(parts) > 2:
            secs += parts[len(parts)-3] * 3600

        return secs

    def to_hms(self, seconds):
        """Convert seconds to HH:MM:SS
        """
        seconds, sec = divmod(float(seconds), 60)
        hr, min = divmod(seconds, 60)

        return "%d:%02d:%02d" % (hr, min, sec)

    def extract_tracks(self):
        """Try different methods to extract tracks metadata
        """
        print("[ydl] Extracting tracks metadata")

        self.tracks = []
        if os.path.exists(self.audio_file):
            self.tracks = self.extract_tracks_from_chapters()
        elif self.config.get('verbose'):
            print("[ydl] Audio file not found, won't look for chapters")

        if len(self.tracks) == 0:
            if self.config.get('verbose'):
                print("[ydl] Chapters not found, trying video description")
            self.tracks = self.extract_tracktimes_from_string(
                self.info.get('description'))

        if len(self.tracks) > 0:
            self.extract_tracks_cleanup()

        common_metadata = self.get_common_metadata()

        for i in range(0, len(self.tracks) - 1):
            self.tracks[i].update(common_metadata)

    def get_tracklist(self):
        output = []
        if len(self.tracks) > 1:
            for track in self.tracks:
                output.append("[ydl] %03d: %s (%s - %s)" % (
                    track['track'],
                    track['title'],
                    self.to_hms(track['start']),
                    self.to_hms(track['end'])))
        else:
            for track in self.tracks:
                output.append("[ydl] %s (%s - %s)" % (
                    track['title'],
                    self.to_hms(track['start']),
                    self.to_hms(track['end'])))

        return "\n".join(output)

    def extract_tracks_from_chapters(self):
        """Read chapters tags on file to find times and metadata
        """
        tracks = []
        ffprobe_cmd = ['ffprobe', '-i', self.audio_file]
        info = str(subprocess.run(ffprobe_cmd,
            stderr=subprocess.PIPE).stderr)

        chapters_regex = r'\s+Chapter\s+' + \
            r'#(?P<track>[:0-9]+).*?' + \
            r'start\s+(?P<start>[0-9.]+).*?' + \
            r'end\s+(?P<end>[0-9.]+).*?' + \
            r'Metadata:(?P<metadata>\\n' + \
                r'\s+(?P<key>\S+)\s+:' + \
                r'\s+(?P<value>.*?)' + \
            r'\\n)+?'
        regex = re.compile(chapters_regex, re.DOTALL)
        for fields in re.findall(regex, info):
            trackno = int(re.sub(r'[^0-9]', '', fields[0])) + 1

            track = {
                'track': trackno,
                'start': fields[1],
                'end': fields[2],
            }
            index = 4
            while index < len(fields) - 1:
                track[self.clean_str(fields[index])] = \
                    self.clean_str(fields[index + 1])
                index += 2
            tracks.append(track)

        return tracks

    def extract_tracktimes_from_string(self, s):
        """Try to find HH:MM patterns as track times on description
        """
        tracks_regex = \
            r'^(.*?)(?P<time>[0-9]?[0-9]?:?[012345]?[0-9]:[012345][0-9])(.*)$'
        regex = re.compile(tracks_regex, re.MULTILINE)
        items = re.findall(regex, s)

        tracks = []
        skipped = end = index = 0
        indexes = len(items)

        while index < indexes:
            start = self.to_seconds(items[index][1])
            if index == indexes - 1:
                end = self.info.get('duration') # total file duration
            else:
                end = self.to_seconds(items[index + 1][1]) - 0.05

            if start > end:
                print('[ydl] Skipping track %d: incorrect timing' % \
                    int(index + 1))
                index += 1
                skipped += 1
                continue

            # track times can be at the beginning or end of the line
            title = '%s %s' % (items[index][0], items[index][2])
            title = self.clean_str(title)

            track = {
                'track': index - skipped + 1,
                'start': start,
                'end': end,
                'title': title
            }
            tracks.append(track)
            index += 1

        return tracks

    def extract_tracks_cleanup(self):
        """Clean tracks after extraction process
        """
        # remove track number from the beginning
        regex = re.compile(r'^\s*?[0-9]+\s*?[^0-9a-zA-Z]*?\s*?')
        for i in range(0, len(self.tracks)):
            self.tracks[i]['title'] = \
                regex.sub('', self.tracks[i]['title']).strip()

    def set_single_file_data(self):
        artist, title = self.parse_title()
        self.tracks = [{
            'artist': artist,
            'title': title,
            'start': 0,
            'end': self.info.get('duration') - 0.05
        }]

    def write_dummy_mp3(self):
        """Create dummy mp3 files to test an import into beets
        """
        if not os.path.exists(self.outdir):
            os.mkdir(self.outdir)

        if len(self.tracks) > 0:
            self.write_dummy_mp3_tracks()
        else:
            self.write_dummy_mp3_file()

    def write_dummy_mp3_tracks(self):
        for track in self.tracks:
            self.write_dummy_mp3_file(track)

    def write_dummy_mp3_file(self, track=False):
        if self.is_album():
            outmp3 = '%s/%03d-%s%s' % (self.outdir,
                track['track'], self.info.get('id'), self.audio_file_ext)
            outwav = '%s/%03d-%s%s' % (self.outdir,
                track['track'], self.info.get('id'), '.wav')
            outdat = outwav + ".dat"
        else:
            outmp3 = '%s/%s%s' % (self.outdir,
                self.info.get('id'), self.audio_file_ext)
            outwav = '%s/%s%s' % (self.outdir, self.info.get('id'), '.wav')
            outdat = outwav + ".dat"

        with open(outdat, 'w') as out:
            out.truncate()
            out.write("; SampleRate 8000\n")
            samples = (track['end'] - track['start']) * 8000
            i = 0
            for i in range(0, int(samples)):
                out.write("%f\t0\n" % (i / 8000))
                i += 1

        sox_cmd = ['sox', outdat, '-c', '2',
                '-r', '44100', '-e', 'signed-integer', outwav]

        ffmpeg_cmd = ['ffmpeg', '-y', '-i', outwav, '-vn', '-ar',
            '44100', '-ac', '1', '-ab', '8k']
        for k in track.keys():
            if k == 'track':
                value = str(track[k])
            else:
                value = '"' + str(track[k]) + '"'
            ffmpeg_cmd.extend(['-metadata', '%s=%s' % (k, value)])
        ffmpeg_cmd.append(outmp3)

        for cmd in (sox_cmd, ffmpeg_cmd):
            subprocess.run(cmd, stderr=subprocess.PIPE,
                stdout=subprocess.PIPE)
