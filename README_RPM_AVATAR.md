# ReadyPlayerMe Avatar Setup Guide

## Quick Setup

### 1. Get Your ReadyPlayerMe Avatar
1. Go to [ReadyPlayerMe](https://readyplayer.me/)
2. Create or customize your character
3. Download the GLB file (not the .rrc file)
4. Copy the GLB file to `static/models/` directory

### 2. Update Avatar Configuration
Edit `static/js/rpm_avatar.js` and update the avatar URL:

```javascript
// Replace this line with your avatar's path
const avatarUrl = '/static/models/your-character.glb';
```

### 3. Alternative: Use ReadyPlayerMe CDN URL
If you want to use the ReadyPlayerMe CDN directly:

```javascript
const avatarUrl = 'https://models.readyplayer.me/YOUR_AVATAR_ID.glb';
```

### 4. Supported Features
- ✅ Lip-sync with audio
- ✅ Emotion-based expressions
- ✅ Head tracking
- ✅ Breathing animations
- ✅ Viseme-based mouth shapes

### 5. Customization Options
You can customize the avatar behavior in `rpm_avatar.js`:
- Emotion blendshapes
- Viseme mappings
- Animation speeds
- Camera positioning
- Lighting setup

## Troubleshooting

### Avatar Not Loading
- Check the GLB file path
- Ensure Three.js and GLTFLoader are loaded
- Check browser console for errors

### No Lip-sync
- Verify audio context is enabled
- Check if blendshapes are available in your model
- Ensure TTS is working

### Performance Issues
- Reduce shadow map quality
- Lower pixel ratio
- Simplify avatar model

## Advanced Features

### Custom Blendshapes
Your ReadyPlayerMe avatar should include these blendshapes for best results:
- Mouth shapes (visemes)
- Brow expressions
- Eye movements
- Facial expressions

### Animation Clips
Add custom animations to your avatar:
- Idle breathing
- Talking gestures
- Emotional reactions
- Head movements

## File Structure
```
static/
├── models/
│   └── your-character.glb    # Your ReadyPlayerMe avatar
├── js/
│   └── rpm_avatar.js         # Avatar controller
└── audio/                    # Generated TTS files
```

## Next Steps
1. Test the avatar with different emotions
2. Adjust lighting and camera angles
3. Customize blendshape intensities
4. Add custom animations if needed
