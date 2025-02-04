#!python3.10

#   MIT License
#
#   Copyright (c) 2023 ZFTurbo - Start the project MVSEP-MDX23 (music separation model)
#   Copyright (c) 2023 Jarredou - Did all the job for Inference !!
#   Copyright (c) 2023 Captain FLAM - Heavily modified ! (GUI, sequential processing, ...)
#
#   https://github.com/ZFTurbo/MVSEP-MDX23-music-separation-model
#   https://github.com/jarredou/MVSEP-MDX23-Colab_v2/
#   https://github.com/Captain-FLAM/KaraFan


import os, gc, io, sys, csv, base64, argparse, requests
import regex as re
import numpy as np
import onnxruntime as ort
import torch, torch.nn as nn

import librosa, soundfile as sf
from pydub import AudioSegment

from time import time

# ONLY for MDX23C models
#  import yaml
#  from ml_collections import ConfigDict

import ipywidgets as widgets
from IPython.display import display, HTML
import contextlib
# from tqdm.auto import tqdm  # Auto : Progress Bar in GUI with ipywidgets
# from tqdm.contrib import DummyTqdmFile

import App.settings, App.audio_utils, App.compare

# from App.tfc_tdf_v3 import TFC_TDF_net

EXTRACT_VOCALS = 1
EXTRACT_INSTRU = 2
FILTER_AUDIO = 3

class Conv_TDF_net_trim_model(nn.Module):

	def __init__(self, device, target_stem, neuron_blocks, model_params, hop=1024):

		super(Conv_TDF_net_trim_model, self).__init__()
		
		self.dim_c = 4
		self.dim_f = model_params['dim_F_set']
		self.dim_t = 2 ** model_params['dim_T_set']
		self.n_fft = model_params['N_FFT_scale']
		self.hop = hop
		self.n_bins = self.n_fft // 2 + 1
		self.chunk_size = hop * (self.dim_t - 1)
		self.window = torch.hann_window(window_length=self.n_fft, periodic=True).to(device)
		self.target_stem = target_stem

		out_c = self.dim_c * 4 if target_stem == '*' else self.dim_c
		self.freq_pad = torch.zeros([1, out_c, self.n_bins - self.dim_f, self.dim_t]).to(device)
		
  		# Only used by "forward()" method
		# self.n = neuron_blocks // 2

	def stft(self, x):
		x = x.reshape([-1, self.chunk_size])
		x = torch.stft(x, n_fft=self.n_fft, hop_length=self.hop, window=self.window, center=True, return_complex=True)
		x = torch.view_as_real(x)
		x = x.permute([0, 3, 1, 2])
		x = x.reshape([-1, 2, 2, self.n_bins, self.dim_t]).reshape([-1, self.dim_c, self.n_bins, self.dim_t])
		return x[:, :, :self.dim_f]

	def istft(self, x, freq_pad=None):
		freq_pad = self.freq_pad.repeat([x.shape[0], 1, 1, 1]) if freq_pad is None else freq_pad
		x = torch.cat([x, freq_pad], -2)
		x = x.reshape([-1, 2, 2, self.n_bins, self.dim_t]).reshape([-1, 2, self.n_bins, self.dim_t])
		x = x.permute([0, 2, 3, 1])
		x = x.contiguous()
		x = torch.view_as_complex(x)
		x = torch.istft(x, n_fft=self.n_fft, hop_length=self.hop, window=self.window, center=True)
		return x.reshape([-1, 2, self.chunk_size])

	# Not used : only for training Models !
	#
	# def forward(self, x):
	# 	x = self.first_conv(x)
	# 	x = x.transpose(-1, -2)
	#
	# 	ds_outputs = []
	# 	for i in range(self.n):
	# 		x = self.ds_dense[i](x)
	# 		ds_outputs.append(x)
	# 		x = self.ds[i](x)
	#
	# 	x = self.mid_dense(x)
	# 	for i in range(self.n):
	# 		x = self.us[i](x)
	# 		x *= ds_outputs[-i - 1]
	# 		x = self.us_dense[i](x)
	#
	# 	x = x.transpose(-1, -2)
	# 	x = self.final_conv(x)
	# 	return x

def get_models(device, model_params, stem):
	# ??? NOT so simple ... ???
	# FFT = 7680  --> Narrow Band
	# FFT = 6144  --> FULL Band
	model = Conv_TDF_net_trim_model(
		device,
		# I suppose you can use '*' to get both vocals and instrum, with the new MDX23C model ...
		'vocals' if stem == 'Vocals' else 'instrum',
		11,
		model_params
	)
	return [model]

# def demix_base_mdxv3(config, model, mix, device, overlap):
# 	mix = torch.tensor(mix, dtype=torch.float32)
# 	try:
# 		S = model.num_target_instruments
# 	except Exception as e:
# 		S = model.module.num_target_instruments

# 	mdx_window_size = config.inference.dim_t
	
# 	# batch_size = config.inference.batch_size
# 	batch_size = 1
# 	C = config.audio.hop_length * (mdx_window_size - 1)
	
# 	H = C // overlap
# 	L = mix.shape[1]
# 	pad_size = H - (L - C) % H
# 	mix = torch.cat([torch.zeros(2, C - H), mix, torch.zeros(2, pad_size + C - H)], 1)
# 	mix = mix.to(device)

# 	chunks = []
# 	i = 0
# 	while i + C <= mix.shape[1]:
# 		chunks.append(mix[:, i:i + C])
# 		i += H
# 	chunks = torch.stack(chunks)

# 	batches = []
# 	i = 0
# 	while i < len(chunks):
# 		batches.append(chunks[i:i + batch_size])
# 		i = i + batch_size

# 	X = torch.zeros(S, 2, C - H) if S > 1 else torch.zeros(2, C - H)
# 	X = X.to(device)

# 	with torch.cuda.amp.autocast():
# 		with torch.no_grad():
# 			for batch in tqdm(batches, ncols=60):
# 				# self.running_inference_progress_bar(len(batches))
# 				x = model(batch)
# 				for w in x:
# 					a = X[..., :-(C - H)]
# 					b = X[..., -(C - H):] + w[..., :(C - H)]
# 					c = w[..., (C - H):]
# 					X = torch.cat([a, b, c], -1)

# 	estimated_sources = X[..., C - H:-(pad_size + C - H)] / overlap

# 	if S > 1:
# 		return {k: v for k, v in zip(config.training.instruments, estimated_sources.cpu().numpy())}
	
# 	est_s = estimated_sources.cpu().numpy()
# 	return est_s

# def demix_full_mdx23c(mix, device, overlap):
# 	model_folder = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "Models")

# 	remote_url_mdxv3 = 'https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/MDX23C_D1581.ckpt'
# 	remote_url_conf = 'https://raw.githubusercontent.com/Anjok07/ultimatevocalremovergui/new-patch-3-20/models/MDX_Net_Models/model_data/mdx_c_configs/model_2_stem_061321.yaml'
# 	if not os.path.isfile(os.path.join(model_folder, 'MDX23C_D1581.ckpt')):
# 		torch.hub.download_url_to_file(remote_url_mdxv3, os.path.join(model_folder, 'MDX23C_D1581.ckpt'))
# 	if not os.path.isfile(os.path.join(model_folder, 'model_2_stem_061321.yaml')):
# 		torch.hub.download_url_to_file(remote_url_conf, os.path.join(model_folder, 'model_2_stem_061321.yaml'))

# 	with open(os.path.join(model_folder, 'model_2_stem_061321.yaml')) as f:
# 		config = ConfigDict(yaml.load(f, Loader=yaml.FullLoader))

# 	model = TFC_TDF_net(config)
# 	model.load_state_dict(torch.load(os.path.join(model_folder, 'MDX23C_D1581.ckpt')))
# 	device = torch.device(device)
# 	model = model.to(device)
# 	model.eval()

# 	sources = demix_base_mdxv3(config, model, mix, device, overlap)
# 	del model
# 	gc.collect()

# 	return sources

def demix_base(mix, device, models, infer_session):
	sources = []
	n_sample = mix.shape[1]
	for model in models:
		trim = model.n_fft // 2
		gen_size = model.chunk_size - 2 * trim
		pad = gen_size - n_sample % gen_size
		mix_p = np.concatenate(
			(
				np.zeros((2, trim)),
				mix,
				np.zeros((2, pad)),
				np.zeros((2, trim))
			), 1
		)

		mix_waves = []
		i = 0
		while i < n_sample + pad:
			waves = np.array(mix_p[:, i:i + model.chunk_size])
			mix_waves.append(waves)
			i += gen_size
		mix_waves = np.array(mix_waves)
		mix_waves = torch.tensor(mix_waves, dtype=torch.float32).to(device)

		try:
			with torch.no_grad():
				_ort = infer_session
				stft_res = model.stft(mix_waves)
				res = _ort.run(None, {'input': stft_res.cpu().numpy()})[0]
				ten = torch.tensor(res)
				tar_waves = model.istft(ten.to(device))
				tar_waves = tar_waves.cpu()
				tar_signal = tar_waves[:, :, trim:-trim].transpose(0, 1).reshape(2, -1).numpy()[:, :-pad]

			sources.append(tar_signal)

		except Exception as e:
			print("\n\nError in demix_base() with Torch : ", e)
			Exit_Notebook()
	
	return np.array(sources)


class MusicSeparationModel:

	def __init__(self, options):

		# In case of changes, don't forget to update the function in GUI !!
		# - on_Del_Vocals_clicked()
		# - on_Del_Music_clicked()
		self.AudioFiles = [
			"NORMALIZED",
			"Music extract",
			"Vocal extract",
			"Ensemble Vocal",
			"Bleedings in Vocal",
			"Vocal FINAL",
			"Music FINAL",
		]
		self.AudioFiles_Mandatory = [1, 2, 5, 6]  # Vocal & Music Extract, Vocal & Music FINAL
		
		# Load Status Led icons
		with open(os.path.join(options['Project'], "images", "Led_Yellow.png"), 'rb') as file:
			self.Led_Yellow = file.read()
		with open(os.path.join(options['Project'], "images", "Led_Red.png"), 'rb') as file:
			self.Led_Red = file.read()

		self.Status_ON = False
		self.Options = options
		self.CONSOLE = options['CONSOLE']
		self.Status  = options['Status']
		self.Progress = options['Progress']

		self.output = os.path.join(options['Gdrive'], options['output'])
		
#		self.preset_genre	= options['preset_genre']
		self.shifts_vocals	= options['shifts_vocals']
		self.shifts_instru	= options['shifts_instru']
		self.shifts_filter	= options['shifts_filter']
#		self.overlap_MDXv3	= int(options['overlap_MDXv3'])
		self.normalize		= options['normalize']
		self.large_gpu		= options['large_gpu']

		self.DEBUG		= options['DEBUG']
		self.TEST_MODE	= options['TEST_MODE']
		self.GOD_MODE	= options['GOD_MODE']
		self.PREVIEWS	= options['PREVIEWS']
			
		self.device = 'cpu'
		if torch.cuda.is_available():  self.device = 'cuda:0'
		print("Use device -> " + self.device.upper())
		
		if self.device == 'cpu':
			print('<div style="font-size:20px;font-weight:bold;color:#f00;background-color:#fff;">Warning ! CPU is used instead of GPU for processing.<br>Will be very slow !!</div>')
		
		if self.device == 'cpu':
			self.chunk_size = 200000000
			self.providers = ["CPUExecutionProvider"]
		else:
			self.chunk_size = 1000000
			self.providers = ["CUDAExecutionProvider"]

		if 'chunk_size' in options:
			self.chunk_size = int(options['chunk_size'])
		
#		if self.overlap_MDXv3 > 40:		self.overlap_MDXv3 = 40
#		if self.overlap_MDXv3 < 1:		self.overlap_MDXv3 = 1

#		if self.bigshifts_MDX > 41:		self.bigshifts_MDX = 41
#		if self.bigshifts_MDX < 1:		self.bigshifts_MDX = 1

		# MDX-B models initialization

		self.models = { 'vocals': [], 'instrum': [], 'filters': [] }
		self.MDX = {}

		# Load Models parameters
		with open(os.path.join(options['Project'], "App", "Models_DATA.csv")) as csvfile:
			reader = csv.DictReader(csvfile, quoting=csv.QUOTE_ALL)
			for row in reader:
				# ignore "Other" stems for now !
				name = row['Name']
				if name == options['vocals_1'] or name == options['vocals_2']:
					self.models['vocals'].append(row)
				elif name == options['instru_1']:
					self.models['instrum'].append(row)
				
				# Special case for "Filters" : can be Vocal or Instrumental !
				if name == options['filter_1'] or name == options['filter_2'] or name == options['filter_3'] or name == options['filter_4']:
					self.models['filters'].append(row)

		# Download Models to :
		models_path	= os.path.join(options['Gdrive'], "KaraFan_user", "Models")

		# IMPORTANT : Volume Compensations are specific for each model AND each song (different re-mastering(s) in Studio) !!!

		for stem in self.models:
			for model in self.models[stem]:
				# Compensations in dB are taken into account over Standard Compensations !!
				if model['Comp_dB'] == "":
					model['Compensation'] = float(model['Compensation'])
				else:
					model['Compensation'] = 10 ** ( float(model['Comp_dB']) / 20)
				
				model['Cut_OFF']		= int(model['Cut_OFF'])
				model['N_FFT_scale']	= int(model['N_FFT_scale'])
				model['dim_F_set']		= int(model['dim_F_set'])
				model['dim_T_set']		= int(model['dim_T_set'])
				
				model['PATH'] = Download_Model(model, models_path, self.CONSOLE, self.Progress)
		
		# Load Models
		if self.large_gpu: 
			print("Large GPU mode is enabled : Loading models now...")

			for stem in self.models:
				for model in self.models[stem]:  self.Load_MDX(model)
	
	# ******************************************************************
	# ****    This is the MAGIC RECIPE , the heart of KaraFan !!    ****
	# ******************************************************************

	def SEPARATE(self, file):
		"""
		Implements the sound separation for a single sound file
		"""
		
		name = os.path.splitext(os.path.basename(file))[0]
		if self.CONSOLE:
			print("Go with : <b>" + name + "</b>")
		else:
			print("Go with : " + name)

		# Create a folder based on input audio file's name
		self.song_output_path = os.path.join(self.output, name)
		if not os.path.exists(self.song_output_path): os.makedirs(self.song_output_path)
		
		# TODO : sr = None --> uses the native sampling rate (if 48 Khz or 96 Khz), maybe not good for MDX models ??
		original_audio, self.sample_rate = librosa.load(file, mono=False, sr = 44100)  # Resample to 44.1 Khz
		
		# Convert mono to stereo (if needed)
		if len(original_audio.shape) == 1:
			original_audio = np.stack([original_audio, original_audio], axis=0)

		print(f"Input audio : {original_audio.shape} - Sample rate : {self.sample_rate}")
		
		# ****  START PROCESSING  ****

		if self.normalize:
			normalized = self.Check_Already_Processed(0)

			if normalized is None:
				print("► Normalizing audio")
				normalized = App.audio_utils.Normalize(original_audio)

				self.Save_Audio(0, normalized)
		else:
			normalized = original_audio
		
		# print("► Processing vocals with MDX23C model")

		# sources3 = demix_full_mdx23c(normalized, self.device, self.overlap_MDXv3)
		# vocals3 = (match_array_shapes(sources3['Vocals'], normalized) \
		# 		+ Pass_filter('lowpass', 14700, normalized - match_array_shapes(sources3['Instrumental'], normalized), 44100)) / 2
		
		# if self.DEBUG:
		#	self.Save_Audio("Vocal_MDX23C", vocals3)
		
		# Extract Music with MDX models
		instrum_extract = []
		for model in self.models['instrum']:
			audio = self.Check_Already_Processed(1, model['Name'])
			if audio is None:
				audio = self.Extract_with_Model(EXTRACT_INSTRU, normalized, model)
				
				# DON'T Apply silence filter !!
				audio = audio * model['Compensation']    # Volume Compensation
				
				self.Save_Audio(1, audio, model['Name'])
			
			instrum_extract.append(audio)
			
		# TODO : Make Ensemble Music ???

		# Extract Vocals with MDX models
		vocals_extract = []
		for model in self.models['vocals']:
			audio = self.Check_Already_Processed(2, model['Name'])
			if audio is None:
				audio = self.Extract_with_Model(EXTRACT_VOCALS, normalized, model)

				audio = audio * model['Compensation']    # Volume Compensation
				audio = App.audio_utils.Silent(audio, self.sample_rate)  # Apply silence filter

				self.Save_Audio(2, audio, model['Name'])
			
			vocals_extract.append(audio)
		
		# Make Ensemble Vocals
		print("► Make Ensemble Vocals")

		vocals_ensemble = App.audio_utils.Make_Ensemble('Max Spec', vocals_extract)

		# vocals_ensemble = App.utils.Silent(vocals_ensemble, self.sample_rate)  # Apply silence filter
		
		self.Save_Audio(3, vocals_ensemble)
		
		del vocals_extract;  gc.collect()
		
		# Pass Vocals through Music Filters
		if len(self.models['filters']) > 0:
			
			filters = []
			for model in self.models['filters']:
				audio = self.Check_Already_Processed(4, model['Name'])
				if audio is None:
					audio = self.Extract_with_Model(FILTER_AUDIO, vocals_ensemble, model)

					audio = audio * model['Compensation']    # Volume Compensation

					# If model Stem is Vocals, substraction is needed !
					if model['Stem'] != "Instrumental":  audio = vocals_ensemble - audio

					audio = App.audio_utils.Silent(audio, self.sample_rate, -45)  # Apply silence filter : -45 dB !

					self.Save_Audio(4, audio, model['Name'])
				
				filters.append(audio)

			# Make Ensemble Vocals
			print("► Make Ensemble Filters")

			filters_ensemble = App.audio_utils.Make_Ensemble('Max Spec', filters)

			#  Remove instrumental Bleedings
			vocals_ensemble -= filters_ensemble
			
			del filters;  gc.collect()

		# Save Vocals FINAL
		print("► Save Vocals FINAL !")

		vocals_ensemble = App.audio_utils.Pass_filter('highpass', 85, vocals_ensemble, self.sample_rate)

		self.Save_Audio(5, vocals_ensemble)
		
		# Repair Music
		print("► Get Music by substracting Vocals from Original audio")
		instrum_final = normalized - vocals_ensemble

		print("► Repair Instrumental with first Music Extractions")
		for audio in instrum_extract:
			audio = App.audio_utils.Pass_filter('highpass', 30, audio, self.sample_rate)
			instrum_final = App.audio_utils.Make_Ensemble('Max Spec', [instrum_final, audio])
		
		del instrum_extract;  gc.collect()


		# Apply silence filter : -61 dB !
		instrum_final = App.audio_utils.Silent(instrum_final, self.sample_rate, threshold_db = -61)

		# Save Music FINAL
		print("► Save Music FINAL !")
		self.Save_Audio(6, instrum_final)
		
		#**********************************
		#****  TESTING for DEVELOPERS  ****
		#**********************************
		
		# The "song_output_path" contains the NAME of the song to compare within the "Multi-Song" folder
		# That's all !!
		if name.startswith("SDR_"):

			print("----------------------------------------")
			App.compare.SDR(self.song_output_path, self.Options['Gdrive'])
		
			# And to Re-process immediately a file :
			#os.remove(os.path.join(self.song_output_path, "2 - Vocal extract - (Kim Vocal 2).flac"))
			
			# OR all files :
			#for file in os.listdir(self.song_output_path):
			#	os.remove(os.path.join(self.song_output_path, file))

		# TESTS - Examples (with old version of KaraFan 1.0)
		
		# instrum = instrum / self.model_instrum['Compensation']
		# self.Save_Audio("Sub - 1", normalized - (instrum * 1.0235))
		# self.Save_Audio("Sub - 2", normalized - (instrum * 1.0240))
		# self.Save_Audio("Sub - 3", normalized - (instrum * 1.0245))

		# vocals_final = vocals_final / self.model_vocals['Compensation']
		# instrum_final_1 = normalized - (vocals_final * 1.0082)
		# instrum_final_2 = normalized - (vocals_final * 1.0085)
		# instrum_final_3 = normalized - (vocals_final * 1.0088)
		# self.Save_Audio("Music - Test 1", instrum_final_1)
		# self.Save_Audio("Music - Test 2", instrum_final_2)
		# self.Save_Audio("Music - Test 3", instrum_final_3)


	def Update_Status(self):
		self.Status.value = self.Led_Red if self.Status_ON else self.Led_Yellow
		self.Status_ON = not self.Status_ON

	def Load_MDX(self, model):
		name = model['Name']
		if name not in self.MDX:
			self.MDX[name] = {}
			self.MDX[name]['model'] = get_models(self.device, model, model['Stem'])
			self.MDX[name]['inference'] = ort.InferenceSession(
				model['PATH'],
				providers = self.providers,
				provider_options = [{"device_id": 0}]
			)
	
	def Kill_MDX(self, model_name):
		if model_name in self.MDX:
			del self.MDX[model_name]['inference']
			del self.MDX[model_name]['model']
			del self.MDX[model_name]
			gc.collect()

	def raise_aicrowd_error(self, msg):
		# Will be used by the evaluator to provide logs, DO NOT CHANGE
		raise NameError(msg)
	
		
	def Show_Preview(self, name, audio):

		name = os.path.splitext(name)[0]
		
		with self.CONSOLE:
			audio_mp3 = io.BytesIO()
			audio_mp3.name = "Preview.mp3"
			
			# Get the first 60 seconds of the audio
			audio = audio[:, :int(60.3 * self.sample_rate)]

			# Convert audio to PCM_16 audio data (bytes)
			audio_tmp = (audio.T * 32768).astype(np.int16)  # 2 ^15

			audio_segment = AudioSegment(
				audio_tmp.tobytes(),
				channels = 2,
				frame_rate = self.sample_rate,
				sample_width = 2  # sample width (in bytes)
			)

			# audio_segment.export(audio_mp3, format='mp3', bitrate='192k', codec='libmp3lame')
			audio_segment.export(audio_mp3, format='mp3', bitrate='192k', codec='libshine')
			# audio_mp3.seek(0)

			display(HTML(
				'<div class="player"><div>'+ name +'</div><audio controls preload="metadata" src="data:audio/mp3;base64,' \
				+ base64.b64encode(audio_mp3.getvalue()).decode('utf-8') +'"></audio></div>'))

			# audio_mp3.close()

	def Check_Already_Processed(self, key, model_name = "", just_check = False):
		"""
		if GOD MODE :
			- Check if audio file is already processed, and if so, load it.
			- Return AUDIO loaded, or NONE if not found.
		Else :
			- Return NONE.
		Key :
			index of AudioFiles list or "str" (direct filename for test mode)
		"""
		self.Update_Status()
		
		if type(key) is int:
			filename = self.AudioFiles[key]
			if self.DEBUG:  filename = f"{key} - {filename}"
		else:
			filename = key

		if model_name != "":  filename += " - ("+ model_name +")"

		match self.Options['output_format']:
			case 'PCM_16':	filename += '.wav'
			case 'FLOAT':	filename += '.wav'
			case "FLAC":	filename += '.flac'
			case 'MP3':		filename += '.mp3'

		file = os.path.join(self.song_output_path, filename)
		
		if (self.GOD_MODE or (type(key) is int and key in self.AudioFiles_Mandatory)) and os.path.isfile(file):
			
			if just_check:  return True
			
			print(filename + " --> Loading ...")
			audio, _ = librosa.load(file, mono=False, sr=self.sample_rate)
			
			# Preview Audio file
			if self.PREVIEWS and self.CONSOLE:  self.Show_Preview(filename, audio)

			return audio
		
		return None
	
	def Save_Audio(self, key, audio, model_name = ""):
		"""
		Key : index of AudioFiles list or "str" (direct filename for test mode)
		"""
		
		# Save only mandatory files if not in DEBUG mode
		if not self.DEBUG and type(key) is int and key not in self.AudioFiles_Mandatory:  return

		if type(key) is int:
			filename = self.AudioFiles[key]
			if self.DEBUG:  filename = f"{key} - {filename}"
		else:
			filename = key

		if model_name != "":  filename += " - ("+ model_name +")"

		match self.Options['output_format']:
			case 'PCM_16':	filename += '.wav'
			case 'FLOAT':	filename += '.wav'
			case "FLAC":	filename += '.flac'
			case 'MP3':		filename += '.mp3'

		file = os.path.join(self.song_output_path, filename)
		
		# Save as WAV
		match self.Options['output_format']:
			case 'PCM_16':
				sf.write(file, audio.T, self.sample_rate, subtype='PCM_16')
			case 'FLOAT':
				sf.write(file, audio.T, self.sample_rate, subtype='FLOAT')
			case "FLAC":
				sf.write(file, audio.T, self.sample_rate, format='flac', subtype='PCM_24')
			case 'MP3':
				# Convert audio to PCM_16 audio data (bytes)
				audio_tmp = (audio.T * 32768).astype(np.int16)  # 2 ^15

				audio_segment = AudioSegment(
					audio_tmp.tobytes(),
					channels = 2,
					frame_rate = self.sample_rate,
					sample_width = 2  # sample width (in bytes)
				)

				# about VBR/CBR/ABR		: https://trac.ffmpeg.org/wiki/Encode/MP3
				# about ffmpeg wrapper	: http://ffmpeg.org/ffmpeg-codecs.html#libmp3lame-1
				# recommended settings	: https://wiki.hydrogenaud.io/index.php?title=LAME#Recommended_encoder_settings

				# 320k is mandatory, else there is a weird cutoff @ 16khz with VBR parameters = ['-q','0'] !!
				# (equivalent to lame "-V0" - 220-260 kbps , 245 kbps average)
				# And also, parameters = ['-joint_stereo', '0'] (Separated stereo channels)
				# is WORSE than "Joint Stereo" for High Frequencies !
				# So let's use it by default for MP3 encoding !!

				audio_segment.export(file, format='mp3', bitrate='320k', codec='libmp3lame')
		
		# Preview Audio file
		if self.PREVIEWS and self.CONSOLE:  self.Show_Preview(filename, audio)

	def Match_Freq_CutOFF(self, audio1, audio2, sample_rate):
		# This option matches the Primary stem frequency cut-off to the Secondary stem frequency cut-off
		# (if the Primary stem frequency cut-off is lower than the Secondary stem frequency cut-off)
	
		# Get the Primary stem frequency cut-off
		# freq_cut_off1 = Get_Freq_CutOFF(audio1, sample_rate)
		# freq_cut_off2 = Get_Freq_CutOFF(audio2, sample_rate)

		# # Match the Primary stem frequency cut-off to the Secondary stem frequency cut-off
		# if freq_cut_off1 < freq_cut_off2:
		# 	audio1 = Match_Freq_CutOFF(audio1, freq_cut_off2, sample_rate)

		return audio1
	
	def Extract_with_Model(self, type, audio, model):
		"""
		Explication from "Jarredou" about the 2 passes :

		This helps reduce/remove the noise added by the MDX models,
		since the phase is inverted before processing and restored afterward in one of the two passes.
		When they are added together, only the MDX noise is out of phase and gets removed,
		while the rest regains its original gain (0.5 + 0.5).
		ZFTurbo also added this to Demucs in the original MVSep-MDX23 code.

		Jarredou -> I've never really tested whether it's really useful for Demucs or not, though.
		Captain-FLAM -> I've tested it, and it's really useful : suppress noise between ~ -42 dB and -58 dB !
		"""
		name = model['Name']

		if type == EXTRACT_VOCALS:
			bigshifts = self.shifts_vocals;  text = f'► Extract Vocals with "{name}"'
		elif type == EXTRACT_INSTRU:
			bigshifts = self.shifts_instru;  text = f'► Extract Music with "{name}"'
		elif type == FILTER_AUDIO:	
			bigshifts = self.shifts_filter;  text = f'► Filter Vocals with "{name}"'
		
		if not self.large_gpu:
			print(f'Large GPU is disabled : Loading model "{name}" now...')
			self.Load_MDX(model)
		
		mdx_model = self.MDX[name]['model']
		inference = self.MDX[name]['inference']

		# ONLY 1 Pass, for testing purposes
		if self.TEST_MODE:
			print(text)
			source = self.demix_full(audio, mdx_model, inference, bigshifts)[0]
		else:
			print(text +" (Pass 1)")
			source = 0.5 * -self.demix_full(-audio, mdx_model, inference, bigshifts)[0]

			print(text +" (Pass 2)")
			source += 0.5 * self.demix_full(audio, mdx_model, inference, bigshifts)[0]

		# Automatic SRS
		if model['Cut_OFF'] > 0:
			
			bigshifts = bigshifts // 4
			if bigshifts < 1:  bigshifts = 1  # must not be <= 0 !

			pitch = 6 if model['Cut_OFF'] < 17000 else 5

			# ONLY 1 Pass, for testing purposes
			if self.TEST_MODE:
				print(text + " -> SRS")
				source_SRS = App.audio_utils.Change_sample_rate( self.demix_full(
					App.audio_utils.Change_sample_rate( audio, pitch, 4), mdx_model, inference, bigshifts)[0], 4, pitch)
			else:
				print(text +" -> SRS (Pass 1)")
				source_SRS = 0.5 * App.audio_utils.Change_sample_rate( -self.demix_full(
					App.audio_utils.Change_sample_rate( -audio, pitch, 4), mdx_model, inference, bigshifts)[0], 4, pitch)

				print(text +" -> SRS (Pass 2)")
				source_SRS += 0.5 * App.audio_utils.Change_sample_rate( self.demix_full(
					App.audio_utils.Change_sample_rate( audio, pitch, 4), mdx_model, inference, bigshifts)[0], 4, pitch)

			# old formula :  vocals = Linkwitz_Riley_filter(vocals.T, 12000, 'lowpass') + Linkwitz_Riley_filter((3 * vocals_SRS.T) / 4, 12000, 'highpass')
			# *3/4 = Dynamic SRS personal taste of "Jarredou", to avoid too much SRS noise
			# He also told me that 12 Khz cut-off was setted for MDX23C model, but now I use the REAL cut-off of MDX models !

			cutoff = model['Cut_OFF'] - 2700

			# Check if source_SRS is not longer than source
			source_SRS = App.audio_utils.match_array_shapes(source_SRS, source)

			source = App.audio_utils.Linkwitz_Riley_filter(source, cutoff, 'lowpass', self.sample_rate, order = 4) \
				   + App.audio_utils.Linkwitz_Riley_filter(source_SRS, cutoff, 'highpass', self.sample_rate, order = 4)
			source = source.T

		if not self.large_gpu:  self.Kill_MDX(name)

		# TODO : Implement band Pass filter
		#
		# Band Cut OFF
		# Vocals : high : 85 - 100 Hz, low : 20 KHz
		# Music  : high : 30 -  50 Hz, low : 18-20 KHz
		#
		# Voix masculine :
		#
		# Minimale : 85 Hz.
		# Fondamentale : 180 Hz
		# Maximale (y compris les harmoniques) : 14 kHz.
		#
		# Voix féminine :
		#
		# Minimale : 165 Hz.
		# Fondamentale : 255 Hz
		# Maximale (y compris les harmoniques) : 16 kHz.
		#
		# Voix d'enfants :
		#
		# Minimale : 250 Hz.
		# Fondamentale : 400 Hz
		# Maximale (y compris les harmoniques) : 20 kHz ou plus.

		return source
	
	def demix_full(self, mix, use_model, infer_session, bigshifts):
		
		step = int(self.chunk_size)
		mix_length = mix.shape[1] / 44100

		if bigshifts < 1:  bigshifts = 1  # must not be <= 0 !
		if bigshifts > int(mix_length):  bigshifts = int(mix_length - 1)
		results = []
		shifts  = [x for x in range(bigshifts)]
		
		# Kept in case of Colab policy change for using GUI
		# and we need back to old "stdout" redirection
		#
		# with self.CONSOLE if self.CONSOLE else stdout_redirect_tqdm() as output:
			# dynamic_ncols is mandatory for stdout_redirect_tqdm()
			# for shift in tqdm(shifts, file=output, ncols=40, unit="Big shift", mininterval=1.0, dynamic_ncols=True):

		# with self.CONSOLE if self.CONSOLE else stdout_redirect_tqdm() as output:
		
		self.Progress.reset(len(shifts), unit="Big shift")

		for shift in shifts:
			
			self.Update_Status()

			shift_samples = int(shift * 44100)
			# print(f"shift_samples = {shift_samples}")
			
			shifted_mix = np.concatenate((mix[:, -shift_samples:], mix[:, :-shift_samples]), axis=-1)
			# print(f"shifted_mix shape = {shifted_mix.shape}")
			result = np.zeros((1, 2, shifted_mix.shape[-1]), dtype=np.float32)
			divider = np.zeros((1, 2, shifted_mix.shape[-1]), dtype=np.float32)

			total = 0
			for i in range(0, shifted_mix.shape[-1], step):
				total += 1

				start = i
				end = min(i + self.chunk_size, shifted_mix.shape[-1])
				mix_part = shifted_mix[:, start:end]
				# print(f"mix_part shape = {mix_part.shape}")
				sources = demix_base(mix_part, self.device, use_model, infer_session)
				result[..., start:end] += sources
				# print(f"result shape = {result.shape}")
				divider[..., start:end] += 1
			
			result /= divider
			# print(f"result shape = {result.shape}")
			result = np.concatenate((result[..., shift_samples:], result[..., :shift_samples]), axis=-1)
			results.append(result)

			self.Progress.update()
			
		results = np.mean(results, axis=0)
		return results
	
	#----

def Download_Model(model, models_path, CONSOLE = None, PROGRESS = None):
	
	name		= model['Name']
	repo_file	= model['Repo_FileName']
	filename	= re.sub(r"^(UVR-MDX-NET-|UVR_MDXNET_|\d_)*", "", repo_file)
	file_path	= os.path.join(models_path, filename)

	if not os.path.isfile(file_path):
		print(f'Downloading model : "{name}" ...')

		remote_url = 'https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/' + repo_file
		try:
			response = requests.get(remote_url, stream=True)
			response.raise_for_status()  # Raise an exception in case of HTTP error code
			
			if response.status_code == 200:
				
				total_size = int(response.headers.get('content-length', 0)) // 1048576  # MB
				PROGRESS.reset(total_size, unit="MB")
				
				with open(file_path, 'wb') as file:

					# Kept in case of Colab policy change for using GUI
					# and we need back to old "stdout" redirection
					#
					# with CONSOLE if CONSOLE else stdout_redirect_tqdm() as output:
					#	with tqdm(
					#		file=output, total=total_size,
					#		unit='B', unit_scale=True, unit_divisor=1024,
					#		ncols=40, dynamic_ncols=True, mininterval=1.0
					#	) as bar:

					for data in response.iter_content(chunk_size=1048576):
						# bar.update(len(data))
						PROGRESS.update()
						file.write(data)
			else:
				print(f'Download of model "{name}" FAILED !!')
				Exit_Notebook()
		
		except (requests.exceptions.RequestException, requests.exceptions.ChunkedEncodingError) as e:
			print(f'Error during Downloading "{name}" !!\n\n{e}')
			if os.path.exists(file_path):  os.remove(file_path)
			Exit_Notebook()
	
	return file_path  # Path to this model


# Redirect "Print" to the console widgets (or stdout)
class CustomPrint:
	def __init__(self, console):
		self.CONSOLE = console

	def write(self, text):
		with self.CONSOLE:
			display(HTML('<div class="console">'+ text +'</div>'))

	def flush(self):
		pass

# Kept in case of Colab policy change for using GUI
# and we need back to old "stdout" redirection
#
# Redirect "Print" with tqdm progress bar
# @contextlib.contextmanager
# def stdout_redirect_tqdm():
# 	orig_out_err = sys.stdout, sys.stderr
# 	try:
# 		sys.stdout, sys.stderr = map(DummyTqdmFile, orig_out_err)
# 		yield orig_out_err[0]
# 	# Relay exceptions
# 	except Exception as exc:
# 		raise exc
# 	# Always restore sys.stdout/err if necessary
# 	finally:
# 		sys.stdout, sys.stderr = orig_out_err


def Process(options):

	start_time = time()
	
	if 'CONSOLE' in options and not options['CONSOLE'] is None:
		sys.stdout = CustomPrint(options['CONSOLE'])

	if len(options['input']) == 0:
		print('Error : You have NO file to process in your "input" folder !!');  return
	
	model = None
	model = MusicSeparationModel(options)

	# Process each audio file
	for file in options['input']:
		
		if not os.path.isfile(file):
			print('Error. No such file : {}. Please check path !'.format(file))
			continue
		
		model.SEPARATE(file)
	
	# Free & Release GPU memory
	if torch.cuda.is_available():
		torch.cuda.empty_cache()
		torch.cuda.ipc_collect()
		
	elapsed_time = time() - start_time
	minutes = int(elapsed_time // 60)
	seconds = int(elapsed_time % 60)
	print('-> Processing DONE !')
	print('Elapsed Time : {:02d}:{:02d} min.'.format(minutes, seconds))
	
	Exit_Notebook()


# Kill GPU !!! (especially on Laptop)
def Exit_Notebook():
	gc.collect()
	os._exit(0)


if __name__ == '__main__':
	"""
	Example of usage :
		python inference.py
		--input mixture.wav mixture1.wav
		--output_format MP3
		--overlap_MDX 0.8
		--chunk_size 500000
		--DEBUG
	"""

	print("For now, the command line is not available !")
	print("Please use the GUI instead !")
	exit(0)
	
	m = argparse.ArgumentParser()
	m.add_argument('--input', nargs='+', type=str, help='Input audio file or location. You can provide multiple files at once.', required=True)
	m.add_argument('--output', type=str, help='Output folder location for extracted audio files results.')
	m.add_argument('--use_config', action='store_true', help='Use "Config_PC.ini" instead of specifying all options in command line.', default=False)
	m.add_argument('--output_format', type=str, help='Output audio format : "FLAC" (24 bits), "MP3" (CBR 320 kbps), "PCM_16" or "FLOAT" (WAV - PCM 16 bits / FLOAT 32 bits).', default='FLAC')
#	m.add_argument('--preset_genre', type=str, help='Genre of music to automatically select the best A.I models.', default='Pop Rock')
	m.add_argument('--model_instrum', type=str, help='MDX A.I Instrumental model NAME : Replace "spaces" in model\'s name by underscore "_".', default='Instrum HQ 3')
	m.add_argument('--model_vocals',  type=str, help='MDX A.I Vocals model NAME : Replace "spaces" in model\'s name by underscore "_".', default='Kim Vocal 2')
	m.add_argument('--bigshifts_MDX', type=int, help='Managing MDX "BigShifts" trick value.', default=12)
	m.add_argument('--overlap_MDX', type=float, help='Overlap of splited audio for heavy models. Closer to 1.0 - slower.', default=0.8)
#	m.add_argument('--overlap_MDXv3', type=int, help='MDXv3 overlap', default=8)
	m.add_argument('--chunk_size', type=int, help='Chunk size for ONNX models. Set lower to reduce GPU memory consumption OR if you have GPU memory errors !. Default: 500000', default=500000)
	m.add_argument('--use_SRS', action='store_true', help='Use "SRS" vocal 2nd pass : can be useful for high vocals (Soprano by e.g)', default=False)
	m.add_argument('--large_gpu', action='store_true', help='It will store all models on GPU for faster processing of multiple audio files. Requires more GB of free GPU memory.', default=False)
	m.add_argument('--TEST_MODE', action='store_true', help='For testing only : Extract with A.I models with 1 pass instead of 2 passes.\nThe quality will be badder (due to low noise added by MDX models) !', default=False)
	m.add_argument('--DEBUG', action='store_true', help='This option will save all intermediate audio files to compare with the final result.', default=False)
	m.add_argument('--GOD_MODE', action='store_true', help='Give you the GOD\'s POWER : each audio file is reloaded IF it was created before,\nNO NEED to process it again and again !!\nYou\'ll be warned : You have to delete each file that you want to re-process MANUALLY !', default=False)
	
	options = m.parse_args().__dict__

	# We are on PC
	Project = os.getcwd()  # Get the current path
	Gdrive  = os.path.dirname(Project)  # Get parent directory

	if options['use_config'] == True:
		
		cmd_input = options['input']

		config = App.settings.Load(Gdrive, False)
		options = App.settings.Convert_to_Options(config)

		options['input'] = cmd_input
	
	elif options['output'] is None:
		print("Error !! You must specify an output folder !")
		exit(0)

	options['Gdrive'] = Gdrive
	options['Project'] = Project
	options['CONSOLE'] = None
	options['PREVIEWS'] = False

	# Create missing folders
	folder = os.path.join(Gdrive, "KaraFan_user")
	os.makedirs(folder, exist_ok=True)
	os.makedirs(os.path.join(folder, "Models"), exist_ok=True)

	Process(options)
