# Configuration GitHub Actions — Déploiement

**RACI :** DevOps pilote le processus ; Pentester assiste sur la sécurité (secrets, accès SSH).

## 1. Ajouter les secrets

1. Va sur https://github.com/LucasTymen/Job_Search_Agent_System
2. **Settings** → **Secrets and variables** → **Actions**
3. **New repository secret** — ajoute ces 3 secrets :

| Nom | Valeur | Exemple |
|-----|--------|---------|
| `SSH_HOST` | IP du serveur Contabo | `173.249.4.106` |
| `SSH_USER` | Utilisateur SSH | `root` |
| `SSH_PRIVATE_KEY` | Contenu complet de ta clé privée | Copie-colle tout le fichier `~/.ssh/id_ed25519_contabo` ou `id_rsa_contabo` (y compris `-----BEGIN ... KEY-----` et `-----END ...`) |

## 2. Vérifier la clé sur le serveur

La clé **publique** correspondante doit être dans `~/.ssh/authorized_keys` sur le serveur :

```bash
ssh root@173.249.4.106 "cat ~/.ssh/authorized_keys"
```

## 3. Déclencher le déploiement

- **Automatique** : chaque push sur `main`
- **Manuel** : onglet **Actions** → **Deploy to Contabo** → **Run workflow**
