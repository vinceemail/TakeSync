# TakeSync for Apple Silicon Macs

Download **TakeSync-0.1.0-macOS-AppleSilicon.zip**, unzip it on your Mac, and move **TakeSync.app** to Applications. No Python or separate FFmpeg installation is needed.

This preview targets Apple M-series Macs and is built and automatically tested on macOS 26. Older macOS releases have not been verified. It is an unsigned/not-notarized preview: macOS may require **System Settings → Privacy & Security → Open Anyway** after the first launch attempt. See [Apple's instructions](https://support.apple.com/102445).

Choose both camera files and the master audio, then click **Analyse & align**. Set **Sync tolerance** in frames, prepare the comparison preview, and export FCPXML to edit with the original media. The preview needs to be prepared again after changing the proposed cuts.

Automated native Mac validation exercises the packaged executable with a fresh cache and a system-only PATH: media probing, audio extraction, musical alignment, master-audio comparison rendering, XML export and UI startup. It does not replace checking lip/instrument sync with your recordings or importing the XML into Resolve/Final Cut on your own Mac.

This is a development preview. Real-time playback of the original camera streams, searching false starts for alternative takes, manual anchor editing and automatic media relinking are not included yet. Save projects while keeping source recordings at their original paths.

The source and dependency notices are in this repository. No recordings or other private workspace files are included in the repository or release.
