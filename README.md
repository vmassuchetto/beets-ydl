![Travis CI](https://api.travis-ci.org/vmassuchetto/beets-ydl.svg?branch=master)

# beets ydl

Download audio from youtube-dl sources and import into beets

    $ beet ydl "https://www.youtube.com/watch?v=wW6ykueIhX8"

    $ beet ls short music for short people

    59 Times the Pain - Short Music for Short People - We Want the Kids
    7 Seconds - Short Music for Short People - F.O.F.O.D.
    88 Fingers Louie - Short Music for Short People - All My Friends Are in Popular Bands
    Adrenalin O.D. - Short Music for Short People - Your Kung Fu Is Old... And Now You Must Die!
    Aerobitch - Short Music for Short People - Steamroller Blues
    [...]

## Installation

    pip install beets-ydl

And enable `ydl` plugin on your `config.yaml` file.

## Configuration

Available options and default values on `config.yaml`:

```yml
plugins: ydl

ydl:
    download: True         # download files from sources after getting information,
    split_files: True      # try to split album files into separate tracks,
    import: True           # import files on youtube-dl after downloading and splitting,
    youtubedl_options: {}  # youtube-dl available options -- https://git.io/fN0c7
    urls: []               # list of default urls to download when no arguments are provided, you
                           # can provide a playlist to get checked every time
```

## How it works

The plugin main goal is to deliver an importable file set to the `beet import`
command, so it will download an audio file, look for a tracklist with track
times in the video description, split the file into per-track files, assign
some basic ID3 tags to them, and finally run `beet import` on
`${BEETS_CONFIG}/ydl-cache/${VIDEO_ID}` directory.

## Tips

- The video title can trick beets to find the correct album, in this case you'll
  have to manually enter a search term

- Use the `bandcamp` plugin for better results

- Use a `.netrc` file to use your own YouTube playlists

  Security discussions apart, you can create a `~/.netrc` with credentials for
  youtube-dl to read.

      machine youtube login somelogin@gmail.com password somepassword

  Check [this entry](https://git.io/fN2TD) on youtube-dl docs for more
  information.

  Like this, you can download private playlists or your subscriptions:

      beet ydl "https://www.youtube.com/feed/subscriptions"

- Download and import later

  To download and split files without importing into beets:

      beet ydl "<source>" --keep-files --no-import

  And later, to import:

      beet ydl "<source>" --no-download --no-split-files

  Like this, you can download a big playlist and then run the beets import
  routine, which requires manual intervention.

- (possibly) enhance audio quality

  beets-ydl uses a proposed [192kbps extractor 'bestaudio'](https://git.io/fN2mJ)
  format because it is more likely that it will find separate audio files on
  sources. Some high quality videos might have better audio quality embedded, so
  it can also make sense to set a higher quality extractor:

  ```yaml
  ydl:
      youtubedl_options:
          format: 'best',
          postprocessors:
              key: 'FFmpegExtractAudio'
              preferredcodec: 'mp3'
              preferredquality: '320'
              nopostoverwrites: True
  ```

  This can, however, end-up with unnecessarily big files that have 320kbps as a
  merely nominal quality. See [this discussion](https://askubuntu.com/q/634584).

## Development

Execute the env script to get into a virtualenv.

    . ./env.develop
