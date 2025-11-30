import time
import multiprocessing
import math

print("=" * 50)
print("CPU STRESS TEST")
print("=" * 50)
print(f"CPU Cores: {multiprocessing.cpu_count()}")
print()

def is_prime(n):
    """Check if a number is prime."""
    if n < 2:
        return False
    for i in range(2, int(math.sqrt(n)) + 1):
        if n % i == 0:
            return False
    return True

def find_primes(start, end):
    """Find all primes in a range."""
    return [n for n in range(start, end) if is_prime(n)]

# Test 1: Single-core prime calculation
print("Test 1: Finding primes up to 100,000 (single core)...")
start = time.time()
primes = find_primes(2, 100_000)
elapsed = time.time() - start
print(f"  Found {len(primes)} primes in {elapsed:.2f} seconds")
print()

# Test 2: Calculate pi using Leibniz formula (CPU intensive)
print("Test 2: Calculating Pi (10 million iterations)...")
start = time.time()
pi = 0
for i in range(10_000_000):
    pi += ((-1) ** i) / (2 * i + 1)
pi *= 4
elapsed = time.time() - start
print(f"  Pi = {pi:.10f}")
print(f"  Time: {elapsed:.2f} seconds")
print()

# Test 3: Matrix operations (pure Python, no numpy)
print("Test 3: Matrix multiplication 200x200 (pure Python)...")
size = 200

def create_matrix(n):
    return [[i * j % 100 for j in range(n)] for i in range(n)]

def multiply_matrices(a, b):
    n = len(a)
    result = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            for k in range(n):
                result[i][j] += a[i][k] * b[k][j]
    return result

start = time.time()
m1 = create_matrix(size)
m2 = create_matrix(size)
result = multiply_matrices(m1, m2)
elapsed = time.time() - start
print(f"  Result[0][0] = {result[0][0]}")
print(f"  Time: {elapsed:.2f} seconds")
print()

print("=" * 50)
print("CPU TEST COMPLETE!")
print("=" * 50)

i = 0
while True:
    i += 1
    print(f"{i}")