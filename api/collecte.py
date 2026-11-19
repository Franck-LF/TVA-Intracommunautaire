


import sys
import time
import requests

import pandas as pd
import logging

sys.path.append('../api')
from validation_structure import normaliser, valider, CONTROLES

PAYS_COUVERTS = list(CONTROLES.keys())
PATH_DATA = "data/"
FILENAME_SOURCE  = "numeros_tva.csv"
FILENAME_RESULTS = "results_benchmark.csv"

# ---------------- Logger ----------------

logging.basicConfig(level = logging.INFO,
                    format = '%(asctime)s %(levelname)s | %(module)s >>> %(message)s',
                    handlers = [logging.FileHandler("log.log"),
                                logging.StreamHandler()]
                    )
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def request_api(df, size_sample):
    '''
        Requête l'API VIES (https://ec.europa.eu/taxation_customs/vies/rest-api/ms)
        Mémorise les verdicts des requêtes et les temps de réponse

        Args:
            df: DataFrame contenant les numéros de TVA
            size_sample: Nombre de numéro à requêter
        
        Returns:
            df_results : DatFrame contenant les verdicts de requêtes et les temps de réponse
            df_numero_to_check : DataFrame avec les pays+numéros qui ont donné des verdicts différents
                                 avec l'API et avec le script "valider" (cas à étudier individuellement)

    '''
    lst_sample = df[['numero_tva_norme', 'Verdict']].sample(size_sample).values.tolist()

    lst_countries, lst_numeros, lst_script_verdict, lst_api_verdict, lst_api_time = [], [], [], [], []
    lst_numeros_to_check = []

    logger.info(f"Lancement de {size_sample} requêtes")
    global_time = time.time()

    for item in lst_sample:
        code_pays, numero = item[0][:2], item[0][2:]
        start = time.time()
        try:
            r = requests.get(f"https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{code_pays}/vat/{numero}", timeout=10)
            elapsed_time = time.time() - start
            if r.status_code == 200:
                logger.info(f"Requête OK pour le code : {item[0]}")
                lst_countries.append(code_pays)
                lst_numeros.append(numero)
                lst_script_verdict.append(item[1])
                lst_api_verdict.append("VALID" if r.json()['isValid'] else "INVALID")
                lst_api_time.append(elapsed_time)

                if r.json()['isValid'] and item[1] != 'VALID':
                    # Si l'API renvoie VALID mais que notre script renvoie INVALID
                    lst_numeros_to_check.append([code_pays, numero])
            else:
                logger.info(f"Requête : {item[0]}")

        except requests.exceptions.Timeout:
            logger.warning(f"Temps de requêtage dépassé pour le code : {item[0]}")
            print(f'Délai dépassé : {item[0]}')

    print(f'Temps de traitement total : {time.time() - global_time}')

    df_results = pd.DataFrame({
        'Pays' : lst_countries,
        'Numero' : lst_numeros,
        'script_verdict' : lst_script_verdict,
        'api_verdict' : lst_api_verdict,
        'api_time' : lst_api_time
    })

    df_numero_to_check = pd.DataFrame({
        'Pays'   : [item[0] for item in lst_numeros_to_check],
        'numero' : [item[1] for item in lst_numeros_to_check]
    })

    print(f'Nombre de requêtes : {size_sample}')
    print(f'Moyenne du temps de requête : {sum(lst_api_time) / size_sample}')
    return df_results, df_numero_to_check




if __name__ == '__main__':

    # On lit les données
    df_csv = pd.read_csv(PATH_DATA + FILENAME_SOURCE, index_col='id', sep=',', keep_default_na = False)
    logger.info(f"Lecture du fichier '{PATH_DATA + FILENAME_SOURCE}'")

    # On supprime les espaces inutiles
    logger.info("Nettoyage des données")
    df_csv['raison_sociale'] = df_csv['raison_sociale'].str.strip()
    df_csv['pays_declare'] = df_csv['pays_declare'].str.strip()

    # On normalie les numéros de TVA (on met les numéros normalisés dans une autre colonne)
    logger.info("Normalisation des données")
    df_csv['numero_tva_norme'] = df_csv['numero_tva'].apply(normaliser)
    
    # On filter les pays couverts
    logger.info("Filtre des données")
    df_csv = df_csv[df_csv['pays_declare'].isin(PAYS_COUVERTS)]

    # On supprime les faux NaN
    df_csv = df_csv[~df_csv['numero_tva_norme'].isin(['NULL', 'NA', 'NAN', ''])]

    # On ajoute le code pays aux numéros qui n'en ont pas (on le prend dans la colonne 'pays_declare')
    logger.info("On ajoute les code_pays aux numéros")
    masque = ~df_csv['numero_tva_norme'].str.match(r'^[A-Za-z]{2}', na=False)

    df_csv.loc[masque, 'numero_tva_norme'] = (
        df_csv.loc[masque, 'pays_declare'] +        
        df_csv.loc[masque, 'numero_tva_norme']
    )

    # On remplace les O par 0
    df_csv['numero_tva_norme'] = df_csv['numero_tva_norme'].str.replace('O', '0', regex=False)

    # On supprime les doublons (sur critère de numéro de TVA seul)
    logger.info("Suppression des doublons")
    df_no_duplicate = df_csv.drop_duplicates(subset=['numero_tva_norme'])

    # On applique la fonction 'Valider'
    logger.info("Application de la fonction de Validation des numéros")
    resultats = df_no_duplicate['numero_tva_norme'].apply(valider)

    df_no_duplicate[['Verdict', 'Motif']] = pd.DataFrame(
        resultats.tolist(),
        index=df_no_duplicate.index,
        columns=['Verdict', 'Motif']
    )

    # On filtre pour ne conserver que les numéros valides (au sens de la syntaxe et structure)
    df_valid = df_no_duplicate[df_no_duplicate['Verdict']]

    # On requête l'API sur un échantillon de numéros dont la syntaxe est valide
    size_sample = 10
    df_results, df_numero_to_check = request_api(df_valid, size_sample)
    df_results.to_csv(PATH_DATA + FILENAME_RESULTS)


