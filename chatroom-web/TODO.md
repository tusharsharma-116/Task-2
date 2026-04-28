# Audio Integration Plan

**Status:** Plan approved.


1. [x] requirements.txt + pip pydub librosa matplotlib soundfile (audio proc)
2. [x] templates/index.html: audio upload + results table (multi-comp, metrics)
3. [x] static/script.js: uploadAudio, audio_results display table
4. [x] app_audio_fixed.py: upload_audio - pydub ≤5MB, MP3 320k-64k, librosa MSE/SNR, spec PNGs, table
5. [x] Run python app_audio_fixed.py, verify http://localhost:5000 (chat, /ai, image, audio table/errors) - test_upload.py succeeded: compression table + specs generated, spectrograms PNG
6. [x] Audio upload fixed & fully working (server receives 'upload_audio', processes via FFmpeg/pydub/librosa, emits results table/MSE/SNR/specs)

**Complete!**


Execute step-by-step.

