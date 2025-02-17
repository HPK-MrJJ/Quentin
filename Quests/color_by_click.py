import cv2

# Load the image
image_path = "watermelon.png"  # Update this if needed
image = cv2.imread(image_path)

# Convert to HSV
hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

# Click event function
def pick_color(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:  # Left-click to pick a color
        hsv_value = hsv_image[y, x]  # Get HSV at clicked pixel
        print(f"Clicked at ({x}, {y}) - HSV Value: {hsv_value}")

# Show the image window
cv2.imshow("Click on a Fruit", image)
cv2.setMouseCallback("Click on a Fruit", pick_color)

# Keep window open until a key is pressed
cv2.waitKey(0)
cv2.destroyAllWindows()
