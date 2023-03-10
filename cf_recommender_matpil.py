# -*- coding: utf-8 -*-
"""cf_recommender_matpil.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/15UI2YzIjGrZDEDOvC7kV5pXLOoavvjuS

# Library Prep.
"""

import pandas as pd
import numpy as np
import warnings
import tensorflow as tf
import matplotlib.pyplot as plt
import seaborn as sns
warnings.filterwarnings('ignore')

import scipy
from scipy.sparse import csr_matrix, coo_matrix
from pandas.api.types import CategoricalDtype

from sklearn.neighbors import NearestNeighbors
from statistics import multimode

"""# Load Data"""

# mengambil data
data = pd.read_csv('data_kuliah_mat.csv')
data.sample(3)

# cek ukuran data
display(data.shape)
print('---------------\n')

# cek data info
display(data.info())
print('---------------\n')

# cek ada tidak missing value
display(data.isnull().sum())

"""# Preprocessing Data
 
Menggenerate fitur-fitur (Feature Engineering ):
- `tahun`: tahun saat pengambilan mata kuliah
- `jenis_smt`: ganjil / genap
- `smt`: semester ke-n saat mata kuliah diambil
- `rumpun`: rumpun yang tersedia (AA: Analisis Aljabar, IK: Ilmu Komputer, MT: Matematika Terapan)

Memfilter Mata Kuliah yang tidak tersedia dalam rumpun, seperti mata kuliah pengayaan / S2
"""

def get_smt(thn, nipd, kode_smt):
  '''fungsi untuk mengekstrak semester'''
  thn_msk = int('20'+str(nipd)[3:5])
  smt = (thn - thn_msk + 1) * 2
  if kode_smt=='Ganjil':
    smt -= 1
  return smt

# dict matpil dan rumpun
rumpun = {
  'KM184711': 'AA', 'KM184712': 'AA', 'KM184713': 'AA',
  'KM184811': 'AA', 'KM184812': 'AA', 'KM184813': 'AA', 'KM184814': 'AA', 'KM184815': 'AA',
  'KM184714': 'MT', 'KM184715': 'MT', 'KM184716': 'MT', 'KM184717': 'MT', 'KM184718': 'MT',
  'KM184719': 'MT', 'KM184720': 'MT', 'KM184721': 'MT', 'KM184731*': 'MT', 
  'KM184816': 'MT', 'KM184817': 'MT', 'KM184818': 'MT', 'KM184819': 'MT', 'KM184820': 'MT',
  'KM184821': 'MT', 'KM184822': 'MT', 'KM184823': 'MT', 'KM184824': 'MT', 'KM184825': 'MT',
  'KM184722': 'IK', 'KM184723': 'IK', 'KM184724': 'IK', 'KM184725': 'IK', 'KM184726': 'IK',
  'KM184826': 'IK', 'KM184827': 'IK', 'KM184828': 'IK', 'KM184829': 'IK', 'KM184830': 'IK', 
  'KM184831': 'IK', 'KM184832': 'IK', 'KM184833': 'IK', 'KM184834': 'IK',
}

# menggenerate tahun
data['tahun'] = data['id_smt'].apply(lambda x: int(str(x)[:-1]))

# menggenerate jenis semester
data['jenis_smt'] = data['id_smt'].apply(lambda x: 'Ganjil' if str(x)[-1]=='1' else 'Genap')

# menggenerate semester
data['smt'] = data.apply(lambda x: get_smt(x.tahun, x.nipd, x.jenis_smt), axis=1)

# menggenerate rumpun
data['rumpun'] = data.kode_mk.replace(rumpun)

# memfilter hanya mata kuliah pilihan program studi S1
data = data[~data.rumpun.str.contains('KM185')] 
peng_idx = data[~data.rumpun.isin(['MT', 'AA', 'IK'])][['rumpun']].index 
data = data[data.rumpun.isin(['MT', 'AA', 'IK'])]
data.sample(3)

# cek info data terbaru
data.info()

# mengecek persebaran data semester mhs saat pengambilan mata kuliah pilihan

plt.style.use('ggplot')
plt.figure(figsize=(8,4))
data.smt.plot.hist(bins=10)
plt.title('Distribusi Semester Pengambilan Mata Kuliah Pilihan')
plt.xlabel('Semester')
plt.ylabel('Jumlah Mahasiswa')

"""> Mata kuliah pilihan paling cepat di semester 3 dan terakhir bisa di semester 14. 
Namun, Kebanyakan diambil di semester 6

## Scoring  


---
* Scenario:  
  * Semester pengambilan awal pada semester ganjil  
  * Secara berurutan semester paling awal diberi rating tertinggi dan paling akhir rating terendah  
  * Dalam satu tahun (smt ganjil-genap) rating sama  
  * Skala tingkat ketertarikan 1-6

---
"""

# perhitungan skor
smt_to_rating = {m:n+1 for n,m in enumerate(sorted(data.smt.unique(), reverse=True)[:-1])}
smt_to_rating = {m:(n+2)//2 for n,m in enumerate(range(data.smt.unique().max(), data.smt.unique().min()-1, -1))}
display(smt_to_rating)

data['tingkat_ketertarikan'] = data.smt.replace(smt_to_rating)
data.sample(3)

# mengecek distribusi tingkat ketertarikan
data.tingkat_ketertarikan.plot.hist(bins=6)
plt.title('Distribusi Tingkat Ketertarikan')
plt.ylabel('Jumlah Mahasiswa')
plt.xlabel('Tingkat Ketertarikan')

"""> Dari plot distribusi tingkat ketertarikan, cenderung miring kanan. Kebanyakan di tingkat ketertarikan 4

# Data Preparation
"""

# filter feature untuk dimodelkan
data_filter = data.drop(columns=['id_smt', 'tahun',	'jenis_smt', 'smt'])
data_filter.sample(3)

"""## Build Sparse Matrix  

Sparse Matrix sebagai input untuk metode Collaborative Filtering
"""

# mengekstrak mahasiswa, matpil unik dan jumlahnya
mhs = data_filter.nipd.unique()
matpil = data_filter.nm_mk.unique()
shape = (len(matpil), len(mhs))

# membuat index mhs dan matpil untuk sparse matrix
mhs_cat = CategoricalDtype(categories=sorted(mhs), ordered=True)
matpil_cat = CategoricalDtype(categories=sorted(matpil), ordered=True)
mhs_index = data_filter.nipd.astype(mhs_cat).cat.codes
matpil_index = data_filter.nm_mk.astype(matpil_cat).cat.codes

# mengonversi ke sparse / COO matrix
coo = coo_matrix((data_filter['tingkat_ketertarikan'], (matpil_index, mhs_index)), shape=shape)
df_coo = pd.DataFrame.sparse.from_spmatrix(coo)

# penyesuaian tipe dat
for col in df_coo.columns:
  df_coo[col] = df_coo[col].values.to_dense().astype(np.float32)

# rename col dan index
df_coo.index = sorted(matpil)
df_coo.columns = sorted(data_filter.nipd.unique())
df_coo.sample(3)

"""## Embedding Preparation"""

# Mengubah nipd menjadi list tanpa nilai yang sama
mhs_ids = data_filter.nipd.unique().tolist()
 
# Melakukan encoding userID
mhs_to_mhs_encoded = {x: i for i, x in enumerate(mhs_ids)}
 
# Melakukan proses encoding angka ke ke nipd
mhs_encoded_to_mhs = {i: x for i, x in enumerate(mhs_ids)}

# Mengubah kode_mk menjadi list tanpa nilai yang sama
nama_mk_ids = data_filter.kode_mk.unique().tolist()
 
# Melakukan proses encoding kode_mk
mk_to_mk_encoded = {x: i for i, x in enumerate(nama_mk_ids)}
 
# Melakukan proses encoding angka ke kode_mk
mk_encoded_to_mk = {i: x for i, x in enumerate(nama_mk_ids)}

# Mapping mhs_ids ke dataframe nipd
data_filter['user'] = data_filter['nipd'].map(mhs_to_mhs_encoded)
 
# Mapping kode_mk ke dataframe 
data_filter['mk'] = data_filter['kode_mk'].map(mk_to_mk_encoded)

# cek dataframe yg telah diupdate
display(data_filter.sample(3))

# Mendapatkan jumlah mhs/user
num_mhs = len(mhs_to_mhs_encoded)
 
# Mendapatkan jumlah mk
num_mk = len(mk_encoded_to_mk)
 
# Mengubah rating menjadi nilai float
data_filter['tingkat_ketertarikan'] = data_filter['tingkat_ketertarikan'].values.astype(np.float32)
 
# Nilai minimum rating
min_rating = min(data_filter['tingkat_ketertarikan'])
 
# Nilai maksimal rating
max_rating = max(data_filter['tingkat_ketertarikan'])
 
print('Jumlah mahasiswa: {} \nJumlah Mata Kuliah Pilihan: {} \nMin Rating: {} \nMax Rating: {}'.format(
    num_mhs, num_mk, min_rating, max_rating
))

"""# Modelling

## Setting
"""

RS = 42
np.random.seed(RS)

"""## Collaborative Filtering - Nearest Neighbors

### Recommender
"""

def matpil_cf_nn_recommender(mhs, num_neighbors, num_recommendation, df_coo=df_coo):
  # copy df
  df_rec = df_coo.copy()

  # menghitung similaritas 
  knn = NearestNeighbors(metric='cosine', algorithm='brute')
  knn.fit(df_coo.values)
  distances, indices = knn.kneighbors(df_coo.values, n_neighbors=num_neighbors)

  # mengambil index mhs dari inputan nipd
  # mhs_index = mhs_cat.categories.get_loc(mhs)
  mhs_index = df_coo.columns.tolist().index(mhs)

  for m,t in list(enumerate(df_coo.index)):

    # mencari matpil yang belum pernah diambil mhs
    if df_coo.iloc[m, mhs_index] == 0:
      sim_matpil = indices[m].tolist()
      matpil_distance = distances[m].tolist()
      
      # mengeluarkan matpil patokan yang dicari kesamaannya
      if m in sim_matpil:
        id_matpil = sim_matpil.index(m)
        sim_matpil.remove(m)
        matpil_distance.pop(id_matpil)

      # mengeluarkan matpil yang paling jauh ketika dianggap mirip karena score 0 
      else:
        sim_matpil = sim_matpil[:num_neighbors-1]
        matpil_distance = matpil_distance[:num_neighbors-1]

      # matpil score = 1 - matpil_distance
      matpil_similarity = [1 - dist for dist in matpil_distance]
      matpil_similarity_ = matpil_similarity.copy()
      nominator = 0

      # untuk setiap matpil yang similar
      for s in range(0, len(matpil_similarity)):
        # cek jika score dari matpil similar 0
        if df_coo.iloc[sim_matpil[s], mhs_index] == 0:
          # jika score = 0, abaikans score dan similarity dalam menghitung prediksi score
          if len(matpil_similarity_) == (num_neighbors-1):
            matpil_similarity_.pop(s)
          else:
            matpil_similarity_.pop(s-(len(matpil_similarity)-len(matpil_similarity_)))
        # jika score != 0, gunakan similarity score ke perhitungan
        else:
          nominator = nominator + matpil_similarity[s] * df_coo.iloc[sim_matpil[s], mhs_index]

      # cek jika jumlah score yg bukan 0 positif
      if len(matpil_similarity_) > 0:
        # cek jika jumlah score positif
        if sum(matpil_similarity_) > 0:
          predicted_score = nominator / sum(matpil_similarity_)
        else:
          predicted_score = 0
      else:
        predicted_score = 0
      
      df_rec.iloc[m, mhs_index] = predicted_score
      # print(f'{matpil_cat.categories[m]} - {mhs_index} - {predicted_score}')

  # display(df_rec[mhs_index].T)
  # recommend_matpil(mhs, num_recommendation, df_rec, df_coo)
  # base_rumpun, rec_rumpun
  return recommend_matpil(mhs, num_recommendation, df_rec, df_coo)
  
def recommend_matpil(mhs, num_recommendation, df_rec, df_coo):
  
  # mengambil index mhs dari inputan nipd
  mhs_index = mhs
  
  base_rumpun = []
  print(f'Mata Kuliah pilihan yang telah diambil oleh {mhs}:')
  for i, m in enumerate(df_coo[df_coo[mhs_index]>0].index.tolist()):
    # print(f'\t{i+1}. {matpil_cat.categories[m]}')
    print(f'\t{i+1}. {m} \ {data_filter[data_filter.nm_mk == m][["rumpun"]].values[0][0]}') #{data_filter[data_filter.nm_mk == m].rumpun[0]}
    base_rumpun += [data_filter[data_filter.nm_mk == m][["rumpun"]].values[0][0]]
  print('\n')

  recommended_matpil = []
  
  for m in df_coo[df_coo[mhs_index]==0].index.tolist():
    # print(m, matpil_cat.categories[m])

    # matpil = matpil_cat.categories.get_loc(m)
    index_df = df_coo.index.tolist().index(m) # mengambil index matpil
    predicted_score = df_rec.iloc[index_df, df_rec.columns.tolist().index(mhs_index)] 
    recommended_matpil.append((m, predicted_score))
  
  sorted_rm = sorted(recommended_matpil, key=lambda x:x[1], reverse=True)
  rec_rumpun = []

  print(f'Top-{num_recommendation} Mata kuliah pilihan yang direkomendasikan:')
  rank = 1
  for matpil in sorted_rm[:num_recommendation]:
    # print(f'\t{rank}. {matpil_cat.categories[matpil[0]]} ({matpil[1]:.2f})')
    print(f'\t{rank}. {matpil[0]} \ {data_filter[data_filter.nm_mk == matpil[0]][["rumpun"]].values[0][0]} ({matpil[1]:.2f})')
    rec_rumpun += [data_filter[data_filter.nm_mk == matpil[0]][["rumpun"]].values[0][0]]
    rank += 1

  return base_rumpun, rec_rumpun

# testing 1
matpil_cf_nn_recommender(6111940000034, 5, 3)

print('\n', '===='*15, '\n')
matpil_cf_nn_recommender(6111740000037, 4, 3)

"""## Collaborative Filtering - Deep Learning

### Prep
"""

# Mengacak dataset
data_filter_ = data_filter.sample(frac=1, random_state=RS).copy()
data_filter_

# Membuat variabel x untuk mencocokkan data user dan mk menjadi satu value
x = data_filter_[['user', 'mk']].values

# Membuat variabel y untuk membuat rating dari hasil 
y = data_filter_['tingkat_ketertarikan'].apply(lambda x: (x - min_rating) / (max_rating - min_rating)).values
 
# Membagi menjadi 80% data train dan 20% data validasi
train_indices = int(0.8 * data_filter_.shape[0])
x_train, x_val, y_train, y_val = (
    x[:train_indices],
    x[train_indices:],
    y[:train_indices],
    y[train_indices:]
)

# cek input 
print(x, y)

act_func = 'elu'
embed_init = 'glorot_normal'


class RecommenderMK(tf.keras.Model):

  # inisialisasi fungsi
  def __init__(self, num_mhs, num_mk, embedding_size, **kwargs):
    super(RecommenderMK, self).__init__(**kwargs)
    self.num_mhs = num_mhs
    self.num_mk = num_mk
    
    self.embedding_size = embedding_size
    self.mhs_embedding = tf.keras.layers.Embedding(# layer embedding
      num_mhs,
      embedding_size,
      embeddings_initializer = embed_init,
      # embeddings_regularizer = tf.keras.regularizers.l2(1e-6)
    )
    self.mhs_bias = tf.keras.layers.Embedding(num_mhs, 1) # layer embedding mk bias
    self.mk_embedding = tf.keras.layers.Embedding(# layer embedding
      num_mk,
      embedding_size,
      embeddings_initializer = embed_init,
      # embeddings_regularizer = tf.keras.regularizers.l2(1e-6)
    )
    self.mk_bias = tf.keras.layers.Embedding(num_mk,1) # layer embedding mk bias

  def call(self, inputs):
    mhs_vector = self.mhs_embedding(inputs[:,0]) # memanggil layer embedding 1
    mhs_bias = self.mhs_bias(inputs[:,0]) # memanggil layer embedding 2
    mk_vector = self.mk_embedding(inputs[:,1]) # memanggil layer embedding 3
    mk_bias = self.mk_bias(inputs[:,1]) # memanggil layer embedding 4
    
    dot_user_mk = tf.tensordot(mhs_vector, mk_vector, 2)

    x = dot_user_mk + mhs_bias + mk_bias 

    return tf.nn.sigmoid(x) #fungsi aktivasi sigmoid

"""### Training"""

tf.keras.backend.clear_session()
tf.random.set_seed(RS)
np.random.seed(RS)

model = RecommenderMK(num_mhs, num_mk, 100) # inisialisasi model
 
# model compile
model.compile(
    loss = tf.keras.losses.MeanSquaredError(),
    optimizer = tf.keras.optimizers.RMSprop(learning_rate=0.003),
    metrics = [tf.keras.metrics.MeanAbsoluteError()]#RootMeanSquaredError()]
)

# training

history = model.fit(
  x = x_train,
  y = y_train,
  batch_size = 8,
  epochs = 50,
  validation_data = (x_val, y_val)
)

plt.plot(history.history['mean_absolute_error'])
plt.plot(history.history['val_mean_absolute_error'])
plt.title('learning process')
plt.ylabel('mae score')
plt.xlabel('epoch')
plt.legend(['train', 'val'], loc='best')
plt.show()

"""### Recommender"""

def matpil_cf_dl_recommender(mhs_id, n_current_mk, top_n, model=model, data_filter=data_filter):

  mk_df = data_filter.drop_duplicates(subset=['kode_mk'])[['kode_mk', 'nm_mk', 'rumpun']].reset_index().drop(columns='index')
  mk_df
  df = data_filter.copy()#pd.read_csv('data_kuliah_mat.csv')
  
  # Mengambil sample user
  mk_visited_by_mhs = df[df.nipd == mhs_id]

  # Operator bitwise (~), bisa diketahui di sini 
  mk_not_visited = mk_df[~mk_df['kode_mk'].isin(mk_visited_by_mhs.kode_mk.values)]['kode_mk']
  mk_not_visited = list(
      set(mk_not_visited)
      .intersection(set(mk_to_mk_encoded.keys()))
  )

  rumpun_from_mk_not_visited = mk_df[mk_df.kode_mk.isin(mk_not_visited)]['rumpun']
  mk_not_visited = [[mk_to_mk_encoded.get(x)] for x in mk_not_visited]

  mhs_encoder = mhs_to_mhs_encoded.get(mhs_id)
  mhs_encoder
  mhs_mk_array = np.hstack(
      ([[mhs_encoder]] * len(mk_not_visited), mk_not_visited)
  )
 
  print(f'Mata Kuliah pilihan yang telah diambil oleh {mhs_id}:')
  top_mk_user = (
    mk_visited_by_mhs.sort_values(
      by = 'tingkat_ketertarikan',
      ascending=False
    )
    .kode_mk.values
  )

  mk_df_rows = mk_df[mk_df['kode_mk'].isin(top_mk_user)]
  for i, row in enumerate(mk_df_rows.itertuples()):
    print(f'\t{i+1}. {row.nm_mk} : {row.rumpun}')

  N = top_n
  ratings = model.predict(mhs_mk_array).flatten()

  top_ratings_indices = ratings.argsort()[-N:][::-1]
  recommended_mk_ids = [
    mk_encoded_to_mk.get(mk_not_visited[x][0]) for x in top_ratings_indices
  ]
  print()
  print(f'Top-{top_n} Mata Kuliah Pilihan yang direkomendasikan:')

  pred_rating = ratings[ratings.argsort()[-N:][::-1]] * (max_rating-min_rating) + min_rating
  recommended_mk = mk_df[mk_df['kode_mk'].isin(recommended_mk_ids)]
  for i, row in enumerate(recommended_mk.itertuples()):
    print(f'\t{i+1}. {row.nm_mk} ({pred_rating[i]:.2f}): {row.rumpun}')

  return mk_df_rows.rumpun.tolist(), recommended_mk.rumpun.tolist()

# testing 1
matpil_cf_dl_recommender(6111940000034, 5, 3)

print('\n', '===='*15, '\n')
matpil_cf_dl_recommender(6111740000037, 4, 3)

"""# Evaluation"""

def recommendation_precision(base_rumpun, rec_rumpun):
  rumpun_utama = multimode(base_rumpun)
  
  if len(rec_rumpun) == 0:
    return 0
    
  if len(rumpun_utama) == 1:
    return rec_rumpun.count(rumpun_utama[0]) / len(rec_rumpun)
  else:
    prec = 0
    for i in range(len(rumpun_utama)):
      prec_temp = rec_rumpun.count(rumpun_utama[i]) / len(rec_rumpun)
      if prec_temp > prec : prec = prec_temp    
    return prec

max_matpil = 6 # default
n_alternatif = 2 
jml_diambil = 1 # jumlah matpil yang telah diambil
list_df_evals = []
n_diambil, n_rekom, cf_nn_precs, cf_dl_precs = [],[],[],[]

for i in range(jml_diambil, max_matpil):
  n_rekomendasi = (max_matpil-i) + 2
  
  total_mk_diambil = data_filter.groupby('nipd').aggregate('count')\
    [['nm_mk']].rename(columns={'nm_mk':'total_mk'})
  df_eval = total_mk_diambil[total_mk_diambil.total_mk==i]#.index[-1]

  cf_nn_precision, cf_dl_precision = [], []

  for id in df_eval.index:
    print('-----'*9)
    print('Collaborative Filtering (Nearest Neighbors)')
    print('-----'*9)
    baseline, recom_cf_nn = matpil_cf_nn_recommender(id, n_rekomendasi+1, n_rekomendasi)
    cf_nn_precision += [recommendation_precision(baseline, recom_cf_nn)]
    print('\n')
    print('-----'*9)
    print('Collaborative Filtering (Deep Learning)')
    print('-----'*9)
    baseline, recom_cf_dl = matpil_cf_dl_recommender(id, n_rekomendasi+1, n_rekomendasi)
    cf_dl_precision += [recommendation_precision(baseline, recom_cf_dl)]

    print('\n')
    print('======='*9)
  
  df_eval['Jml_Rekomendasi'] = [n_rekomendasi] * df_eval.shape[0]
  df_eval[f'CF_NN_Precision_{n_rekomendasi}'] = cf_nn_precision
  df_eval[f'CF_DL_Precision_{n_rekomendasi}'] = cf_dl_precision
  list_df_evals += [df_eval]

  n_diambil += [i]
  n_rekom += [n_rekomendasi]
  cf_nn_precs += [np.mean(cf_nn_precision)*100]
  cf_dl_precs += [np.mean(cf_dl_precision)*100]

df_metrics = pd.DataFrame(
  {
    'N_MatPil_Diambil': n_diambil,
    'N_Rekomendasi': n_rekom,
    'Avg_CF_NN_Precision': cf_nn_precs,
    'Avg_CF_DL_Precision': cf_dl_precs
  }
)

df_metrics

list_df_evals[-1]