<?php
/**
 * Plugin Name: CrossBorder Social Publisher
 * Description: Custom REST endpoint for social post publishing
 * Version: 1.1
 */

define("CB_API_KEY", "cb-social-key-2026");

// Fix: ensure site URL is set before REST API initialization
add_filter("pre_option_home", function() { return "http://localhost:8080"; });
add_filter("pre_option_siteurl", function() { return "http://localhost:8080"; });

add_action("rest_api_init", function () {
    register_rest_route("cb/v1", "/publish", [
        "methods" => "POST",
        "callback" => "cb_publish_post",
        "permission_callback" => function ($request) {
            return $request->get_header("X-CB-API-Key") === CB_API_KEY;
        },
    ]);

    register_rest_route("cb/v1", "/upload-image", [
        "methods" => "POST",
        "callback" => "cb_upload_image",
        "permission_callback" => function ($request) {
            return $request->get_header("X-CB-API-Key") === CB_API_KEY;
        },
    ]);
});

function cb_publish_post($request) {
    $title = sanitize_text_field($request->get_param("title"));
    $content = wp_kses_post($request->get_param("content"));
    $status = sanitize_text_field($request->get_param("status") ?: "draft");

    if (empty($title)) {
        return new WP_Error("missing_data", "title required", ["status" => 400]);
    }

    $post_id = wp_insert_post([
        "post_title" => $title,
        "post_content" => $content,
        "post_status" => $status,
        "post_type" => "post",
        "post_author" => 1,
    ]);

    if (is_wp_error($post_id)) return $post_id;

    return rest_ensure_response([
        "id" => $post_id,
        "title" => get_the_title($post_id),
        "status" => get_post_status($post_id),
        "url" => get_permalink($post_id),
        "edit_url" => admin_url("post.php?post=$post_id&action=edit"),
    ]);
}

function cb_upload_image($request) {
    require_once ABSPATH . "wp-admin/includes/media.php";
    require_once ABSPATH . "wp-admin/includes/file.php";

    $image_url = esc_url_raw($request->get_param("image_url"));
    if (empty($image_url)) {
        return new WP_Error("missing_data", "image_url required", ["status" => 400]);
    }

    $tmp = download_url($image_url);
    if (is_wp_error($tmp)) return $tmp;

    $file_array = ["name" => "social-post-" . time() . ".jpg", "tmp_name" => $tmp];
    $attachment_id = media_handle_sideload($file_array, 0, "Social Image");

    return rest_ensure_response([
        "id" => $attachment_id,
        "url" => wp_get_attachment_url($attachment_id),
    ]);
}
