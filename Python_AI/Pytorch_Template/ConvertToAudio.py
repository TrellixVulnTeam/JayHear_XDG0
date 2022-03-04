import math
import sys
import numpy as np
import librosa
import librosa.display
import scipy
import torch
import soundfile as sf
from sklearn.preprocessing import MinMaxScaler
import matplotlib.pyplot as plt
import Model
from DataLoader import AudioDenoiserDataset
from torch.utils.data import DataLoader
from sklearn.preprocessing import StandardScaler
from JsonParser import JsonParser
import math


class ConvertToAudio:
    def __init__(self, model, combined_audio, clean_audio):
        self.model = model.float()
        self.combined_audio = combined_audio
        self.clean_audio = clean_audio
        self.window = scipy.signal.hamming(256, sym=False)
        self.noisy_log_spec = []
        self.clean_log_spec = []
        self.modeled_audio = 0
        self.clean_phase = None
        self.noisy_phase = None
        self.MinMax = None
        self.temp = 0
        self.clean_temp=0

    def show_spectrogram(self, clean_audio, experiment) -> None:
        fig, ax = plt.subplots(nrows=3, ncols=1, sharex=True)

        img = librosa.display.specshow(librosa.amplitude_to_db(self.clean_log_spec, ref=np.max), y_axis='linear',
                                       x_axis='time',
                                       ax=ax[0], sr=16000, hop_length=round(256 * 0.25))
        ax[0].set_title('Clean Spectrogram')
        ax[0].label_outer()

        img = librosa.display.specshow(self.temp, y_axis='linear',
                                       x_axis='time',
                                       ax=ax[1], sr=16000, hop_length=round(256 * 0.25))
        ax[1].set_title('Noisy Spectrogram')
        ax[1].label_outer()

        denoised_stft = np.abs(librosa.stft(clean_audio, n_fft=256, hop_length=round(256 * 0.25), win_length=256,
                                            window=self.window, center=True))
        img = librosa.display.specshow(librosa.amplitude_to_db(denoised_stft, ref=np.max), y_axis='linear',
                                       x_axis='time',
                                       ax=ax[2], sr=16000, hop_length=round(256 * 0.25))
        ax[2].set_title('Denoised Spectrogram')
        ax[2].label_outer()

        fig.colorbar(img, ax=ax, format="%+2.0f dB")
        plt.savefig("Pytorch_Template/images/" + experiment[:-4])

    def apply_griffin(self, phase_scale=True):
        # self.modeled_audio = self.denormalize(self.modeled_audio)
        if (phase_scale):
            self.modeled_audio = self._phase_aware_scaling(self.modeled_audio, self.clean_phase, self.noisy_phase)
            self.modeled_audio = self.denormalize(self.modeled_audio)
            clean_signal = librosa.istft(librosa.db_to_amplitude(self.modeled_audio), hop_length=round(256 * 0.25),
                                         win_length=256,
                                         window=self.window, center=True)
        else:
            self.modeled_audio = self.denormalize(self.modeled_audio)
            self.modeled_audio=librosa.db_to_amplitude(self.modeled_audio)
            self.modeled_audio=np.squeeze(self.modeled_audio)
            self.modeled_audio=self.modeled_audio*np.exp(1j*self.noisy_phase)
            clean_signal = librosa.istft(self.modeled_audio, hop_length=round(256 * 0.25),
                                         win_length=256,
                                         window=self.window, center=True)
        # print(f'Denoised shape: {clean_signal.shape}')
        return clean_signal

    def _phase_aware_scaling(self, clean_spectral_magnitude, clean_phase, noise_phase):
        assert clean_phase.shape == noise_phase.shape, "Shapes must match."
        return clean_spectral_magnitude * np.cos(clean_phase - noise_phase)

    # def db_to_amp(self):
    #     print(self.model_frames[0])
    #     self.model_log_spec=librosa.db_to_amplitude(self.model_frames[0])
    #     print(self.model_log_spec)

    def normalize(self, array):
        self.MinMax = MinMaxScaler(feature_range=(-1, 1))
        return self.adjust_shape(self.MinMax.fit_transform(array))

    def denormalize(self, norm):
        # array = (norm - self.min_norm) / (self.max_norm - self.min_norm)
        # array = array * (self.max_norm - self.min_norm) + self.min_norm
        return self.MinMax.inverse_transform(norm)

    def add_zeros_to_front(self, array):
        zeros = np.zeros((1, 1, 129, 7))
        array = torch.tensor(np.append(zeros, array, axis=3))
        return array

    def create_frames(self, array, i, single):
        frame = self.model(array.float())
        if i % 100 == 0:
            print(f'Modeling frame: {i}')
        if single:
            frame = frame[0, 0, :]
            frame = frame.detach().numpy().reshape((129, 1))
        else:
            frame = frame[0, 0, :, :]
            frame = frame.detach().numpy()
        return frame

    def your_counter(self, count, stop):
        if stop == count:
            # count = 0 for periodic break
            return True
        else:
            return False
        # if (self.your_counter(count=i, stop=435)):
        #     print('worked')

    def create_batch(self, spec):
        dataset = AudioDenoiserDataset("/home/braden/Environments/Spectrograms/noisy2221_SNRdb_0.0_clnsp2221")
        train_loader = DataLoader(dataset=dataset, batch_size=256, shuffle=False, drop_last=False, num_workers=16)
        batch=[]
        for i, (combined, clean) in enumerate(train_loader):
            combined = combined[:, 1:, :]
            combined, clean=combined.unsqueeze(dim=1).float(), clean.unsqueeze(dim=1).float()
            frames=self.model(combined)
            frames = frames[:, 0, :, :]
            frames = frames.detach().numpy()
            batch.append(frames)
            print(f'Creating batch {i} of data')
        for i, arrays in enumerate(batch):
            for frames in arrays:
                self.modeled_audio = np.append(self.modeled_audio, frames, axis=1)

    def feed_multi_into_model(self):
        self.noisy_log_spec = self.normalize(self.noisy_log_spec[0, 0, :, :])
        self.noisy_log_spec = self.add_zeros_to_front(self.noisy_log_spec)
        self.modeled_audio = np.zeros((129, 1))
        self.create_batch(self.noisy_log_spec)
        # for i in range(0, self.clean_phase.shape[1]):
        #     frame = self.create_frames(self.noisy_log_spec[:, :, :, i:i + 8], i, single=False)
        #     self.modeled_audio = np.append(self.modeled_audio, frame, axis=1)

        self.modeled_audio = self.modeled_audio[:, 1:]  # removes the layer of zeros we initially added

    def feed_single_into_model(self):
        self.modeled_audio = np.zeros((129, 1))
        self.noisy_log_spec = self.normalize(self.noisy_log_spec[0, 0, :, :])
        for i in range(0, self.clean_phase.shape[1]):
            frame = self.create_frames(self.noisy_log_spec[:, :, :, i], i, single=True)
            self.modeled_audio = np.append(self.modeled_audio, frame, axis=1)

        self.modeled_audio = self.modeled_audio[:, 1:]  # removes the layer of zeros we initially added

    def adjust_shape(self, audio):  # Makes numpy input a tensor with dim [Batch, Tensor, height, width]
        audio = torch.tensor(audio)
        audio = audio.unsqueeze(dim=0).float()
        audio = audio.unsqueeze(dim=0).float()
        return audio

    def to_log_spectrogram(self):
        noisy_signal, sr = librosa.load(path=self.combined_audio, sr=8000, dtype='double')
        self.noisy_log_spec = librosa.stft(noisy_signal, n_fft=256, hop_length=round(256 * 0.25), win_length=256,
                                           window=self.window, center=True)
        self.noisy_phase = np.angle(self.noisy_log_spec)
        self.temp = librosa.amplitude_to_db(np.abs(self.noisy_log_spec), ref=np.max)
        self.noisy_log_spec = self.adjust_shape(librosa.amplitude_to_db(np.abs(self.noisy_log_spec)))

        clean_signal, sr = librosa.load(self.clean_audio, 8000, dtype='double')
        self.clean_log_spec = librosa.stft(clean_signal, n_fft=256, hop_length=round(256 * 0.25), win_length=256,
                                           window=self.window, center=True)
        self.clean_temp=librosa.amplitude_to_db(np.abs(self.clean_log_spec))
        self.clean_phase = np.angle(self.clean_log_spec)

    # def convert(self):
    #     mel_spec=self.model(self.combined_audio_array)
    #     mel_spec_np=self.feature_extraction(mel_spec)
    #     clean_audio=librosa.feature.inverse.mel_to_audio(mel_spec_np)
    #     return clean_audio

    # def feature_extraction(self, audio):
    #     audio=audio.cpu().detach().numpy()
    #     audio=audio[0, 0, :, :]
    #     return audio


def load_model(model, config: JsonParser):
    model.load_state_dict(torch.load(config.get_saved_model()))
    return model


def denoise_audio_files(config: JsonParser, device: torch.device):
    print('=> Denoising Audio')
    # model = config.get_model(device, gpu=False)
    model = Model.ConvAutoEncoder8_lightning()
    model = model.load_from_checkpoint(config.get_saved_model())
    # model = load_model(model, config)
    convert = ConvertToAudio(model, config.get_combined_audio(), config.get_clean_audio())
    convert.to_log_spectrogram()
    convert.feed_multi_into_model()
    clean_audio = convert.apply_griffin(phase_scale=False)
    convert.show_spectrogram(clean_audio, config.get_experiment_name())
    sf.write(config.get_denoised_audio(), clean_audio, 8000, 'PCM_24')
    print('=> Denoising Audio Complete')


def main(arguments):
    """Main func."""
    device: torch.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    config: JsonParser = JsonParser(
        '/home/braden/Environments/JayHear/Python_AI/Pytorch_Template/config_files/experiment24.json')
    denoise_audio_files(config, device)


if __name__ == "__main__":
    main(sys.argv[1:])
