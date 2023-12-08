import string
import random

def generate_random_string(size):
    letters = string.ascii_lowercase + string.ascii_uppercase
    return "".join(random.choice(letters) for _ in range(0, size))

def generate_random_integer(min, max):
    return random.randint(min, max)
