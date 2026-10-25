"""Regression coverage for the 4K60 AV1 download that appeared stuck at 82%."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import threading
import time

import pytest

from mediaforge import ffmpeg, web
from mediaforge.downloader import subtitle_tracks_from_info
from mediaforge.downloader import fast_burn_video_format
from mediaforge.jobs import JobManager, diagnostic_source


def test_fast_burn_fetches_a_native_hd_stream_without_changing_the_audio_choice():
    formats=[{'format_id':'4k','vcodec':'av1','acodec':'none','width':3840,'height':2160,'fps':60},
        {'format_id':'hd60','vcodec':'av1','acodec':'none','width':1920,'height':1080,'fps':60},
        {'format_id':'hd30av1','vcodec':'av1','acodec':'none','width':1920,'height':1080,'fps':30},
        {'format_id':'hd30h264','vcodec':'avc1.640028','acodec':'none','width':1920,'height':1080,'fps':30},
        {'format_id':'muxed-dub','vcodec':'h264','acodec':'aac','width':1920,'height':1080,'fps':30}]
    assert fast_burn_video_format({'formats':formats})=='hd30h264'
    assert fast_burn_video_format({'formats':formats[:2]}) is None


@pytest.mark.integration
def test_fast_burn_size_caps_portrait_video_fps_without_enlarging(tmp_path):
    source=tmp_path/'portrait.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=black:size=212x402:rate=60:duration=0.3',
        '-c:v','libx264','-threads','2','-y',str(source)],check=True,capture_output=True)
    caption=tmp_path/'ar.srt';caption.write_text('1\n00:00:00,000 --> 00:00:01,000\nمرحبا بالعالم\n',encoding='utf-8')
    out=tmp_path/'out.mp4'
    ffmpeg.convert(source,out,'mp4',subtitle_path=caption,burn_size='1080')
    video=ffmpeg.probe(out)['video']
    assert (video['width'],video['height'])==(212,402) and video['fps']==pytest.approx(30,abs=.01)


@pytest.mark.parametrize('size,scaled', [('source', False), ('1080', True)])
def test_burning_explicitly_encodes_with_safe_caption_path_and_preserves_source_size(monkeypatch, tmp_path, size, scaled):
    source=tmp_path/'video.mp4';source.touch()
    caption=tmp_path/"Arabic ' commas, Windows path.srt"
    caption.write_text('1\n00:00:00,000 --> 00:00:01,000\nمرحبا بالعالم\n',encoding='utf-8')
    monkeypatch.setattr(ffmpeg,'probe',lambda p:{'duration':1,'video':{'codec':'av1','width':3840,'height':2160,'fps':60},'audio':{'codec':'aac','channels':2}})
    observed=[]
    def run(command,on_line,**kwargs):
        assert (Path(kwargs['cwd'])/'captions.srt').read_text(encoding='utf-8')==caption.read_text(encoding='utf-8')
        observed.append(command)
    monkeypatch.setattr(ffmpeg,'run',run)
    ffmpeg.convert(source,tmp_path/'out.mp4','mp4',subtitle_path=caption,burn_size=size)
    command=observed[0]
    assert command[command.index('-c:v')+1]=='libx264'
    assert command[command.index('-c:a')+1]=='copy'
    assert command[command.index('-tune')+1]=='zerolatency'
    filter_string=command[command.index('-vf')+1]
    assert 'subtitles=filename=captions.srt' in filter_string
    assert ('scale=' in filter_string)==scaled and ('fps=' in filter_string)==scaled


def test_av1_mp4_copy_preserves_resolution_fps_and_reports_progress(monkeypatch, tmp_path):
    source=tmp_path/'source.mkv'
    source.touch()
    monkeypatch.setattr(ffmpeg, 'probe', lambda path:{'duration':688,'format':'matroska','video':{'codec':'av1','pixelFormat':'yuv420p','width':3840,'height':2160,'fps':60},'audio':{'codec':'aac','channels':2}})
    commands=[]
    def run(command,on_line,**kwargs):
        commands.append(command)
        on_line('out_time_us=344000000')
        on_line('progress=end')
    monkeypatch.setattr(ffmpeg,'run',run)
    progress=[]
    ffmpeg.convert(source,tmp_path/'video.mp4','mp4',on_progress=lambda ratio,mode:progress.append((ratio,mode)))
    command=commands[0]
    assert command[command.index('-c:v')+1]=='copy'
    assert '-vf' not in command and '-r' not in command and 'libx264' not in command
    assert any(ratio==.5 for ratio,_ in progress) and progress[-1][0]==1
    assert all('without re-encoding' in mode for _,mode in progress)


def test_ffmpeg_limits_both_input_decoders_and_output_encoder():
    command=ffmpeg.bounded_command(['ffmpeg','-i','first.mp4','-i','audio.m4a','-c:v','libx264','output.mp4'])
    assert command[command.index('-filter_threads')+1]=='1'
    assert command[command.index('-filter_complex_threads')+1]=='1'
    for index,argument in enumerate(command):
        if argument=='-i':
            assert command[index-2:index]==['-threads','2']
    assert command[-3:]==['-threads','2','output.mp4']


def test_arabic_captions_prefer_original_english_over_the_last_dub():
    info={'formats':[{'format_id':'audio-en','acodec':'aac','vcodec':'none','language':'en-US','format_note':'English (US) original (default)'}],
          'automatic_captions':{'ar-orig':[{'ext':'vtt','name':'Arabic (Original)','url':'https://example.test/timedtext?v=video&lang=ar&kind=asr'}],
          'ar':[{'ext':'vtt','name':'Arabic','url':'https://example.test/timedtext?v=video&lang=ar&kind=asr'},
                {'ext':'vtt','name':'Arabic','url':'https://example.test/timedtext?v=video&lang=en&tlang=ar&kind=asr'},
                {'ext':'vtt','name':'Arabic','url':'https://example.test/timedtext?v=video&lang=uk&tlang=ar&kind=asr'}]}}
    tracks=subtitle_tracks_from_info(info)
    original=next(track for track in tracks if track['language']=='ar-orig')
    translated=next(track for track in tracks if track['language']=='ar')
    assert original['sourceLanguage']=='ar' and original['originalCaption'] and not original['translated']
    assert original['label']=='Arabic', 'Original does not mean original video audio'
    assert translated['sourceLanguage']=='en' and translated['translated']
    assert all('lang=en' in entry['url'] for entry in info['automatic_captions']['ar'])


def test_diagnostic_source_keeps_video_identity_without_credentials():
    assert diagnostic_source('https://user:password@www.youtube.com/watch?v=video&token=secret#fragment')=='https://www.youtube.com/watch?v=video'
    assert diagnostic_source('https://example.test/file.mp4?signature=secret')=='https://example.test/file.mp4'
    assert diagnostic_source('https://[')=='(invalid source URL)'


@pytest.mark.integration
def test_real_av1_packets_survive_fast_mp4_save(tmp_path):
    source=tmp_path/'av1.mkv'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=60:duration=0.3',
                    '-threads','2','-c:v','libaom-av1','-cpu-used','8','-crf','40','-y',str(source)],check=True,capture_output=True)
    output=tmp_path/'result.mp4'
    ffmpeg.convert(source,output,'mp4')
    def packets(path):
        data=subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_packets','-show_data_hash','sha256','-of','json',str(path)])
        return [packet['data_hash'] for packet in json.loads(data)['packets']]
    assert packets(source)==packets(output)
    assert ffmpeg.probe(output)['video']['codec']=='av1'
    assert ffmpeg.probe(output)['video']['fps']==pytest.approx(60,abs=.5)
    assert (ffmpeg.probe(output)['video']['width'],ffmpeg.probe(output)['video']['height'])==(160,90)


@pytest.mark.integration
def test_cancel_download_terminates_its_media_process_and_does_not_leave_it_running(monkeypatch):
    manager=JobManager()
    entered=threading.Event()
    children=[]
    popen=subprocess.Popen
    def capture(*args,**kwargs):
        child=popen(*args,**kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(ffmpeg.subprocess,'Popen',capture)
    def work(context):
        def line(value):
            context.write(value)
            if value.startswith('out_time_us='):
                entered.set()
        ffmpeg.run(['ffmpeg','-hide_banner','-nostats','-progress','pipe:1','-re','-f','lavfi','-i',
                    'testsrc2=size=160x90:rate=10:duration=30','-f','null','-'],line,check_cancelled=context.check_cancelled)
        return {}
    job=manager.start('download',work)
    assert entered.wait(10), 'FFmpeg did not begin producing progress'
    app=web.create_app()
    monkeypatch.setattr(web,'jobs',manager)
    response=app.test_client().post(f'/api/jobs/{job.id}/cancel',json={})
    assert response.status_code==200 and response.json['cancelRequested']
    deadline=time.monotonic()+5
    while job.status in {'queued','running'} and time.monotonic()<deadline:
        time.sleep(.05)
    assert job.status=='cancelled'
    assert children and all(child.poll() is not None for child in children), 'Cancel must terminate FFmpeg before reporting completion'
    assert not job.public()['canCancel']


def test_cancellation_cannot_interrupt_publication_or_an_upload():
    from mediaforge.jobs import Job
    manager=JobManager()
    for kind,result in [('render',None),('upload',None),('download',{'cloudDownloadId':'uploaded'})]:
        job=Job(id=kind,kind=kind,status='running',result=result)
        manager._jobs[job.id]=job
        with pytest.raises(ValueError):
            manager.cancel(job.id)
