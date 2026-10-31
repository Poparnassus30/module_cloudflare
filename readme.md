# module_cloudflare — Architecture et spécifications

**Projet :** module_cloudflare  
**Dépôt :** https://github.com/Poparnassus30/module_cloudflare  
**Statut :** Développement initial — V0.1  
**Langage :** Python 3  
**Plateforme :** Cloudflare  
**Date de synthèse :** 31 octobre 2026

---

## 1. Présentation

`module_cloudflare` est un module Python autonome destiné à découvrir, superviser et administrer les ressources Cloudflare associées à une machine.

Il doit permettre de centraliser les informations concernant les tunnels Cloudflare, leurs itinéraires, les services associés et leur état de fonctionnement.

Le module est conçu pour être **indépendant de toute application particulière** et réutilisable dans différents environnements.

Il pourra notamment être intégré à des architectures distribuées, des serveurs personnels, des infrastructures professionnelles ou des applications utilisant Cloudflare.

### Philosophie

**Installer → Détecter → Superviser → Publier.**

L'objectif est de réduire au minimum la configuration manuelle.

L'utilisateur ne doit pas avoir à déclarer individuellement chaque tunnel, chaque domaine ou chaque service.

Le module doit récupérer automatiquement les informations disponibles auprès du système local et de l'API Cloudflare.

---

## 2. Objectifs principaux

### 2.1. Découverte automatique

Le module devra :

- Identifier les processus `cloudflared` actifs sur la machine.
- Détecter les services système associés.
- Identifier les tunnels Cloudflare exécutés localement.
- Récupérer les identifiants des tunnels.
- Lire les configurations locales disponibles.
- Interroger l'API Cloudflare pour récupérer les configurations distantes.
- Identifier les itinéraires publiés et leurs services de destination.

La découverte devra fonctionner sans déclaration manuelle des domaines.

### 2.2. Supervision

Chaque tunnel et chaque service devront être supervisés indépendamment.

Le module devra distinguer :

- L'état du processus `cloudflared`.
- L'état de connexion du tunnel auprès de Cloudflare.
- L'état de chaque service local.
- L'état global du tunnel et de ses services.

Un tunnel peut être connecté alors qu'un service derrière celui-ci est indisponible.

Cette distinction est fondamentale.

### 2.3. Heartbeat

Le module disposera d'un mécanisme périodique de signalement d'état.

Paramètres initialement envisagés :

- Intervalle : 30 secondes.
- Expiration TTL : 120 secondes.
- Publication automatique des états.
- Disparition automatique des états périmés.

Le heartbeat doit permettre de détecter une interruption de communication ou l'arrêt d'une machine.

### 2.4. Centralisation Cloudflare KV

Les états seront publiés dans Cloudflare Workers KV.

Chaque tunnel disposera d'un enregistrement contenant les services découverts et leurs états.

Le module devra générer automatiquement les clés et les données.

Les applications Cloudflare Workers pourront ensuite exploiter ces informations pour la supervision, l'affichage des états ou des décisions applicatives.

**Attention :** Workers KV est un stockage à cohérence éventuelle. Les informations publiées ne doivent pas être considérées comme une mesure instantanée garantie, ni comme un mécanisme de sécurité à lui seul.

---

## 3. Architecture fonctionnelle

```text
                 MACHINE LOCALE
               Linux / Windows / NAS
                         |
                         v
                module_cloudflare
                         |
                 Mini-noyau Python
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
       Discovery       Monitoring     Heartbeat
          |              |              |
          v              v              |
     cloudflared      Services          |
     systemd          TCP/HTTP          |
     Config locale       |              |
          |              |              |
          +--------------+--------------+
                         |
                         v
                  Cloudflare API
                         |
             Tunnels / Configurations
                         |
                         v
                 Registre des états
                         |
                         v
                 Cloudflare KV
                         |
                         v
                 Cloudflare Worker
                         |
                         v
             Applications / Supervision
```

### Responsabilités

**Mini-noyau**

Coordonne le démarrage, la découverte, les contrôles périodiques et la publication des états.

**Discovery**

Identifie les ressources locales et récupère leur configuration auprès de Cloudflare.

**Monitoring**

Vérifie indépendamment la disponibilité des tunnels et des services.

**Heartbeat**

Publie périodiquement les résultats.

**Cloudflare Client**

Centralise les appels à l'API Cloudflare et la gestion des erreurs.

**Configuration**

Fournit les paramètres nécessaires au fonctionnement du module.

---

## 4. Découverte des itinéraires Cloudflare

### 4.1. Problème identifié

Lors des premiers tests sur un serveur Ubuntu, un tunnel Cloudflare fonctionnait avec plusieurs itinéraires publiés.

Cependant, le fichier local `/etc/cloudflared/config.yml` ne contenait qu'une route SSH.

Exemple :

```yaml
tunnel: reinerouge-ssh
credentials-file: /etc/cloudflared/reinerouge-ssh.json

ingress:
  - hostname: reinerouge.poparnassus.fr
    service: ssh://localhost:22
  - service: http_status:404
```

En parallèle, l'interface Cloudflare présentait plusieurs services associés à un tunnel.

### 4.2. Explication

Cloudflare permet la gestion distante de la configuration des tunnels.

Les itinéraires configurés depuis le tableau de bord Cloudflare ne figurent donc pas nécessairement dans le fichier local.

Les journaux `cloudflared` ont notamment montré des événements de mise à jour de configuration.

**Conclusion : la découverte locale seule est insuffisante.**

### 4.3. Solution retenue

Utiliser une découverte hybride :

1. Identifier le tunnel exécuté localement.
2. Récupérer son identifiant.
3. Interroger l'API Cloudflare.
4. Lire les règles `ingress` de sa configuration distante.
5. Construire automatiquement la liste des services à superviser.

Endpoint retenu pour les tunnels gérés à distance :

```http
GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations
```

La réponse contient les informations nécessaires pour récupérer les associations entre domaines et services, lorsque le tunnel utilise une configuration distante.

### 4.4. Exemple de configuration observée

| Domaine | Service |
|---|---|
| reinerouge.poparnassus.fr | http://localhost:8000 |
| jellyfin.poparnassus.fr | http://127.0.0.1:8096 |
| reinerouge-ssh.poparnassus.fr | ssh://localhost:22 |

Ces itinéraires ont été observés dans l'interface Cloudflare.

Leur récupération effective par le module Python reste à valider.

---

## 5. Modèle de supervision

Chaque ressource devra disposer d'un état indépendant.

### Tunnel

États envisagés :

- `connected`
- `disconnected`
- `unknown`

### Service

États envisagés :

- `online`
- `offline`
- `unknown`

### État global

- `online` : tous les services contrôlables répondent.
- `degraded` : certains services répondent et d'autres non.
- `offline` : aucun service contrôlable ne répond ou le tunnel est indisponible.
- `unknown` : informations insuffisantes.

Ces états constituent le modèle fonctionnel initial et pourront être affinés.

Un service non encore déployé pourra ultérieurement disposer d'un état `planned`, à condition que cette intention soit explicitement connue du module.

---

## 6. Format des données KV

Principe retenu : un enregistrement principal par tunnel.

Exemple de clé :

```text
tunnel:<tunnel_uuid>
```

Exemple de valeur :

```json
{
  "tunnel": {
    "id": "example-uuid",
    "status": "connected"
  },
  "services": {
    "app.example.com": {
      "origin": "http://127.0.0.1:8000",
      "status": "online"
    },
    "media.example.com": {
      "origin": "http://127.0.0.1:8096",
      "status": "online"
    },
    "ssh.example.com": {
      "origin": "ssh://localhost:22",
      "status": "offline"
    }
  },
  "overall": "degraded",
  "timestamp": "2026-10-31T09:00:00Z"
}
```

Cet exemple représente le format envisagé, et non un résultat de test réel.

Les clés seront générées automatiquement à partir des ressources découvertes.

Le Worker devra également tenir compte de l'absence d'une clé ou d'une information trop ancienne.

---

## 7. Configuration du module

Le choix retenu est un fichier de configuration local unique.

### Principes

- Configuration indépendante du code source.
- Paramètres documentés directement dans le fichier.
- Exemples intégrés.
- Partie modifiable par l'utilisateur.
- Partie réservée aux données générées automatiquement.
- Conservation de la configuration locale lors des mises à jour Git.

Exemple conceptuel :

```ini
# Configuration utilisateur

TOKEN="your_cloudflare_api_token"
ACCOUNT_ID="your_account_id"

# Identification locale automatique privilégiée
RUNTIME_NAME="auto"

# Heartbeat
HEARTBEAT_INTERVAL=30
HEARTBEAT_TTL=120

# =================================================
# NE RIEN MODIFIER SOUS CETTE LIGNE
# Section générée automatiquement par le programme
# =================================================

__AUTOGENERATED__=true

LAST_UPDATE=""
LAST_STATUS=""
DISCOVERED_ROUTES=""
```

Le format définitif du fichier et son gestionnaire doivent encore être stabilisés.

Les secrets et les données sensibles ne doivent jamais être publiés dans le dépôt Git.

---

## 8. Organisation du code

Une première organisation Python a été envisagée :

```text
module_cloudflare/
|
|-- main.py
|-- module_cloudflare/
|   |-- __init__.py
|   |-- config.py
|   |-- cloudflare_client.py
|
|-- .gitignore
|-- README.md
```

Cette organisation est une cible proposée, et non une confirmation de l'arborescence actuellement présente dans GitHub.

### Classes et méthodes initiales

**CloudflareClient**

Client responsable des communications avec l'API Cloudflare.

Méthodes prévues :

```python
get_tunnel_configuration(tunnel_id)
get_tunnel_routes(tunnel_id)
```

**Config**

Gestionnaire de configuration locale.

Responsabilités :

```python
load_configuration()
rewrite_autogenerated()
```

Les noms exacts et les interfaces pourront évoluer lors de la refactorisation.

---

## 9. Déploiement

Le développement initial s'effectue depuis un poste Windows avec Git.

Le code est ensuite récupéré sur les machines cibles.

### Workflow

```text
Développement Windows
        |
        v
    Git commit
        |
        v
     Git push
        |
        v
      GitHub
        |
        v
     Git pull
        |
        v
  Machine Linux
        |
        v
    Exécution
```

### Environnement de test initial

- Ubuntu
- Python 3.12.3
- Environnement virtuel `venv-cloudflare`
- Bibliothèque `requests` 2.32.5
- `cloudflared` exécuté comme service systemd

Le fonctionnement du service `cloudflared` et son activation au démarrage ont été vérifiés.

---

## 10. État d'avancement

### Réalisé ou identifié

- [x] Création du dépôt GitHub.
- [x] Clonage du dépôt sur le poste de développement.
- [x] Préparation de l'environnement Python Ubuntu.
- [x] Identification du fonctionnement systemd de `cloudflared`.
- [x] Identification du problème des itinéraires distants.
- [x] Définition de la stratégie de découverte hybride.
- [x] Première proposition de classe CloudflareClient.
- [x] Première proposition de gestionnaire Config.

### À réaliser ou valider

- [ ] Stabiliser l'arborescence Python.
- [ ] Corriger les imports et les noms de fichiers.
- [ ] Finaliser le fichier de configuration.
- [ ] Tester l'authentification API Cloudflare.
- [ ] Récupérer réellement les itinéraires publiés.
- [ ] Vérifier la correspondance entre tunnel local et tunnel distant.
- [ ] Implémenter la découverte automatique des tunnels.
- [ ] Implémenter les contrôles de disponibilité des services.
- [ ] Développer le mini-noyau.
- [ ] Développer le heartbeat.
- [ ] Implémenter les écritures Workers KV.
- [ ] Développer la lecture des états côté Worker.
- [ ] Ajouter les tests automatisés.
- [ ] Préparer le lancement automatique du module au démarrage.

---

## 11. Feuille de route

### V0.1 — Découverte des itinéraires

Obtenir depuis une machine la liste exacte des itinéraires associés à son tunnel Cloudflare.

**Critère de validation :** les itinéraires récupérés par Python correspondent à ceux configurés dans Cloudflare.

### V0.2 — Découverte locale automatique

Identifier automatiquement les tunnels actifs et leurs identifiants sans configuration individuelle.

### V0.3 — Supervision des services

Vérifier chaque destination selon son protocole et calculer les états individuels et globaux.

### V0.4 — Mini-noyau et heartbeat

Créer une boucle de supervision autonome, avec journalisation, gestion des erreurs et intervalles configurables.

### V0.5 — Intégration Workers KV

Publier les états automatiquement avec expiration et permettre leur consultation par un Worker.

### V1.0 — Agent autonome

Disposer d'un module réutilisable capable de découvrir, superviser et publier l'état des ressources Cloudflare d'une machine avec une configuration minimale.

---

## 12. Principes de développement

Le développement devra respecter les principes suivants :

**Autonomie :** éviter les déclarations manuelles des ressources détectables.

**Modularité :** séparer découverte, API, supervision, configuration et publication.

**Portabilité :** prévoir plusieurs systèmes d'exploitation.

**Fiabilité :** distinguer un tunnel connecté d'un service réellement disponible.

**Sécurité :** limiter les permissions API, protéger les secrets et éviter toute publication d'informations sensibles.

**Extensibilité :** permettre l'ajout de nouveaux contrôles, de nouvelles ressources Cloudflare et de nouveaux mécanismes de communication.

**Indépendance :** ne créer aucune dépendance fonctionnelle obligatoire envers ReineRouge ou une autre application particulière.

---

## 13. Prochaine étape prioritaire

La priorité immédiate est de finaliser la méthode Python permettant de récupérer les itinéraires d'un tunnel depuis l'API Cloudflare.

Avant d'ajouter le heartbeat ou la supervision avancée, cette fonctionnalité doit être testée sur une machine réelle.

**Objectif du prochain test :**

```text
Tunnel découvert : reinerouge
|
|-- reinerouge.poparnassus.fr
|   -> http://localhost:8000
|
|-- jellyfin.poparnassus.fr
|   -> http://127.0.0.1:8096
|
|-- reinerouge-ssh.poparnassus.fr
|   -> ssh://localhost:22
```

Une fois ce résultat confirmé, le développement pourra progresser vers la supervision automatique et la centralisation des états dans Cloudflare Workers KV.

---

**Vision finale :** faire de `module_cloudflare` un agent autonome, universel et extensible, capable de relier l'état réel d'une infrastructure locale aux services Cloudflare, sans configuration répétitive et sans dépendance à une application spécifique.
