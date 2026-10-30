# Glossaire

[← Accueil](../README.md)

Les mots techniques utilisés dans cette documentation, par ordre alphabétique.

| Mot | Explication simple |
|---|---|
| **A/B (test)** | Comparer deux versions (A et B) qui ne diffèrent que par un seul élément, pour savoir si cet élément change le résultat. |
| **Ancre** | Image de référence fixe, envoyée à chaque demande pour que le style ne « dérive » pas, comme l'ancre d'un bateau. |
| **Animation « en 3 »** | Chaque dessin est montré pendant 3 images de suite. À 24 images par seconde, on voit donc 8 dessins différents par seconde. |
| **API** | Porte d'entrée qui permet à un programme d'utiliser un service sur Internet, par exemple demander un dessin à une IA. Un **appel d'API** est une demande envoyée par cette porte. |
| **Base / finition** | Deux passes de dessin : la base fixe la pose et le costume, la finition ajoute le relief papier. |
| **ComfyUI** | Logiciel qui enchaîne des opérations sur des images sous forme de boîtes reliées par des fils. Dans le projet : accès aux modèles, guides et réinsertion des retouches. Voir le [chapitre 6](06-comfyui.md). |
| **Composition (ou incrustation)** | Poser le personnage détouré sur un décor. |
| **Consigne (prompt)** | Texte qui décrit à l'IA ce qu'on veut obtenir. |
| **Dépôt Git** | Dossier dont Git conserve l'historique complet des versions. GitHub est un site qui héberge des dépôts. |
| **Détourage** | Retirer le fond d'une image pour ne garder que le personnage. |
| **Empreinte (SHA-256)** | Code calculé à partir du contenu d'un fichier. Si un seul pixel change, l'empreinte change : c'est une façon de prouver qu'un fichier est resté identique. |
| **Flow** | Outil de Google qui génère des vidéos par intelligence artificielle. La vidéo de départ du projet en vient. |
| **Flux optique** | Technique qui estime le déplacement des points entre deux images. Dans les zones unies ou cachées, cette estimation peut être ambiguë ou fausse. |
| **Fond vert** | Fond d'une couleur très vive et uniforme, facile à retirer par un programme. Utilisé au cinéma et pour la météo à la télévision. |
| **Frame** | Une image d'une vidéo. |
| **Graine (seed)** | Nombre qui fixe le tirage au sort d'une IA. Avec certains outils, la même graine redonne la même image ; ce n'était pas garanti avec les services utilisés ici. |
| **i/s (images par seconde)** | Nombre d'images affichées chaque seconde. La vidéo du projet est à 24 i/s. |
| **IA générative** | Programme entraîné sur de grandes quantités d'exemples, capable de créer de nouvelles images ou de nouveaux textes. |
| **JPEG / PNG** | Deux formats d'image. Le JPEG réduit la taille du fichier en perdant un peu de détail ; le PNG ne perd rien. |
| **Journal** | Fichier où le programme note chaque action : demande envoyée, réponse reçue, erreur, coût estimé. |
| **Kirigami** | Art japonais de découper et de plier le papier pour créer des formes en relief. |
| **Maillage** | Réseau de points reliés en triangles, posé sur une image. En déplaçant les points, on déforme l'image triangle par triangle. |
| **Masque** | Image en noir et blanc qui indique quelle zone traiter (blanc) et quelle zone laisser intacte (noir). |
| **Modèle** | Le « cerveau » d'une IA, le programme entraîné lui-même. Nano Banana Pro, GPT Image et FLUX sont des modèles. |
| **Multi-tour (conversation)** | Façon d'utiliser une IA en lui renvoyant tout l'échange précédent, pour qu'elle tienne compte du contexte. |
| **Normalisation** | Mettre toutes les images au même format et à la même taille avant de les comparer. |
| **Nœud** | Boîte d’un workflow qui réalise une opération, par exemple charger une image, découper un détail ou appeler une IA. |
| **Partner Node** | Nœud ComfyUI qui appelle un modèle distant et peut consommer des crédits Comfy. |
| **Pixel** | Plus petit point d'une image numérique. Les images de travail du projet font 720 pixels de large sur 1280 de haut. |
| **Planche** | Une seule image qui contient plusieurs dessins, par exemple quatre poses en 2 × 2 cases. |
| **Propagation** | Transporter une matière approuvée d'une image vers les suivantes en la déformant pour suivre le mouvement. |
| **Provision / débit réel** | La provision est le coût estimé à l'avance ; le débit réel est ce que le fournisseur facture vraiment. |
| **Référence (image de)** | Image envoyée à l'IA en plus de la consigne, pour lui montrer une pose, une identité ou un style. |
| **Résidu** | Différence restante après compensation estimée du mouvement. Pour le comparer, il faut le même domaine et le même mouvement ; un flou ou une déformation peuvent aussi le réduire sans améliorer le rendu. |
| **Revue** | Relecture critique d'un travail : vérification des faits, des sources et des chiffres. |
| **Signature (thought signature)** | Donnée opaque et chiffrée associée à certaines parties d'une réponse Google pour conserver du contexte. Dans l'essai conversationnel, elle est renvoyée intacte avec le contenu modèle ; elle ne verrouille pas le style. |
| **Stop-motion** | Technique d'animation où l'on photographie des objets réels en les déplaçant un peu entre chaque photo. |
| **Témoin (de contrôle)** | Élément répété à l'identique dans deux essais pour vérifier si le résultat change. Ici, la pose 9 dessinée dans deux appels. |
| **Timeout (délai dépassé)** | Une demande restée sans réponse au-delà du temps prévu. On ne sait pas si elle a été traitée et facturée. |
| **Token** | Petite unité de texte ou d'image comptée par les services d'IA pour calculer le prix d'une demande. |
| **Vidéo-à-vidéo** | IA qui prend une vidéo entière et la redessine dans un autre style en gardant le mouvement. |
| **Workflow** | Recette de traitement décrite par des nœuds et leurs connexions, enregistrable dans un fichier JSON. |
