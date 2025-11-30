import torch

print("=" * 50)
print("GPU TEST SCRIPT")
print("=" * 50)

# Check if CUDA is available
if torch.cuda.is_available():
    print(f"CUDA is available!")
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    
    # Run a simple GPU computation
    print("\nRunning matrix multiplication on GPU...")
    
    # Create two large matrices on GPU
    size = 5000
    a = torch.randn(size, size, device='cuda')
    b = torch.randn(size, size, device='cuda')
    
    # Warm up
    torch.cuda.synchronize()
    
    # Time the multiplication
    import time
    start = time.time()
    c = torch.matmul(a, b)
    torch.cuda.synchronize()
    elapsed = time.time() - start
    
    print(f"Matrix size: {size}x{size}")
    print(f"Time: {elapsed:.3f} seconds")
    print(f"TFLOPS: {2 * size**3 / elapsed / 1e12:.2f}")
    
    # Memory usage
    print(f"\nGPU Memory Used: {torch.cuda.memory_allocated() / 1e9:.2f} GB")
    print(f"GPU Memory Cached: {torch.cuda.memory_reserved() / 1e9:.2f} GB")
    
    print("\n" + "=" * 50)
    print("GPU TEST PASSED!")
    print("=" * 50)
else:
    print("CUDA is NOT available")
    print("This script requires a GPU with CUDA support")
