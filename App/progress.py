# import ipywidgets as widgets
import time

class Bar:
	def __init__(self, progress_bar, progress_text, unit='iter.'):
		self.value = 0
		self.total = 0
		self.unit = unit
		self.start_time = None

		# Utilisez les widgets de barre de progression et de boîte de texte fournis
		self.progress_bar  = progress_bar
		self.progress_text = progress_text
		self.progress_text.value = "[00:00:00] - &nbsp;&nbsp;0% - 0/0 - 0.00 sec/" + unit

	def reset(self, total, unit=''):
		self.value = 0
		self.total = total
		self.unit = unit
		self.start_time = time.time()
		self.progress_bar.value  = 0
		self.progress_bar.max = total
		self.progress_text.value = f"[00:00:00] - &nbsp;&nbsp;0% - 0/{self.total} - 0.00 sec/{self.unit}"

	def update(self, increment=1):
		self.value += increment

		# Mettez à jour la barre de progression
		self.progress_bar.value = self.value

		# Mettez à jour le texte à côté de la barre de progression
		elapsed_time = time.time() - self.start_time if self.start_time else 0
		if self.value > 0:
			time_per_unit = elapsed_time / self.value
		else:
			time_per_unit = 0
		
		percent = int(100 * self.value / self.total)
		if percent < 10:
			percent = f"&nbsp;&nbsp;{percent}"
		elif percent < 100:
			percent = f"&nbsp;{percent}"
		else:
			percent = f"{percent}"

		download = " MB" if self.unit == "MB" else ""
		text = f"[{time.strftime('%H:%M:%S', time.gmtime(elapsed_time))}] - {percent}% - {self.value}/{self.total}{download} - {time_per_unit:.2f} sec/{self.unit}"
		self.progress_text.value = text

	def close(self):
		# Fermez le layout
		self.layout.close()
