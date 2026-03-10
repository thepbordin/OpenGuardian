import hashlib
from openguardian.config.settings import settings

# For this PoC, we will use the Neo4j password as our per-installation hashing salt.
# In a real application, a separate runtime-generated secret stored independently is better.
SALT = settings.neo4j_password.get_secret_value()

def hash_domain(domain: str) -> str:
    """
    Creates a privacy-preserving salted SHA-256 hash of a domain string.
    
    Args:
        domain (str): The raw domain string (e.g., 'roblox.com')
        
    Returns:
        str: 64-character hex digest of the domain + salt
    """
    normalized_domain = domain.strip().lower()
    payload = f"{normalized_domain}:{SALT}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
