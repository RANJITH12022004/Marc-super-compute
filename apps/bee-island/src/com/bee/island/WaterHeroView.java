package com.bee.island;

import android.content.Context;
import android.util.AttributeSet;

/**
 * Thin deprecated alias for {@link HydrationHeroView}.
 *
 * <p>Kept so existing call sites (IslandService pill/hero stage) keep
 * compiling while new code uses HydrationHeroView directly. All beat
 * logic lives in HydrationHeroView; this class only constructs/delegates.</p>
 */
@Deprecated
public class WaterHeroView extends HydrationHeroView {

    public WaterHeroView(Context context) {
        super(context);
    }

    public WaterHeroView(Context context, AttributeSet attrs) {
        super(context, attrs);
    }
}
